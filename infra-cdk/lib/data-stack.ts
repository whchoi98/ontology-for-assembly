/**
 * DataStack - Neptune + OpenSearch Serverless + S3 + DynamoDB.
 *
 * 리소스:
 * - Neptune cluster (isolated subnet, t3.medium for PoC)
 * - OpenSearch Serverless collection (Nori + KNN hybrid 인덱스)
 * - S3 4개 버킷: raw-docs, uploads, synthetic-data, demo-recordings
 * - DynamoDB 4개: b2b-keys, ad-inventory, ad-impression, reader-profile
 *   (TTL: ad-impression 14일 - ADR-0003 익명성)
 */
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as neptune from 'aws-cdk-lib/aws-neptune';
import * as opensearchserverless from 'aws-cdk-lib/aws-opensearchserverless';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import { Construct } from 'constructs';

export interface DataStackProps extends cdk.StackProps {
  vpc: ec2.IVpc;
  appSg: ec2.ISecurityGroup;
  neptuneSg: ec2.ISecurityGroup;
  osSg: ec2.ISecurityGroup;
  lambdaSg: ec2.ISecurityGroup;
}

export class DataStack extends cdk.Stack {
  public readonly neptuneClusterId: string;
  public readonly neptuneEndpoint: string;
  public readonly openSearchEndpoint: string;
  public readonly rawDocsBucket: s3.IBucket;
  public readonly uploadsBucket: s3.IBucket;
  public readonly syntheticDataBucket: s3.IBucket;
  public readonly b2bKeysTable: dynamodb.ITable;
  public readonly adInventoryTable: dynamodb.ITable;
  public readonly adImpressionTable: dynamodb.ITable;
  public readonly readerProfileTable: dynamodb.ITable;

  constructor(scope: Construct, id: string, props: DataStackProps) {
    super(scope, id, props);

    const { vpc, neptuneSg } = props;
    const account = cdk.Stack.of(this).account;

    // ─── S3 4개 ────────────────────────────────────────────────────────────
    this.rawDocsBucket = new s3.Bucket(this, 'RawDocsBucket', {
      bucketName: `ontology-assembly-dev-raw-docs-${account}`,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      enforceSSL: true,
    });
    this.uploadsBucket = new s3.Bucket(this, 'UploadsBucket', {
      bucketName: `ontology-assembly-dev-uploads-${account}`,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      enforceSSL: true,
    });
    this.syntheticDataBucket = new s3.Bucket(this, 'SyntheticDataBucket', {
      bucketName: `ontology-assembly-dev-synthetic-data-${account}`,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      enforceSSL: true,
    });

    // ─── Neptune (isolated subnet) ─────────────────────────────────────────
    const neptuneSubnetGroup = new neptune.CfnDBSubnetGroup(this, 'NeptuneSubnetGroup', {
      dbSubnetGroupDescription: 'Assembly Neptune isolated subnets',
      subnetIds: vpc.selectSubnets({ subnetType: ec2.SubnetType.PRIVATE_ISOLATED }).subnetIds,
      dbSubnetGroupName: 'assembly-neptune-subnet-group',
    });

    const neptuneCluster = new neptune.CfnDBCluster(this, 'NeptuneCluster', {
      dbClusterIdentifier: 'assembly-neptune-cluster',
      vpcSecurityGroupIds: [neptuneSg.securityGroupId],
      dbSubnetGroupName: neptuneSubnetGroup.dbSubnetGroupName,
      iamAuthEnabled: true,
      storageEncrypted: true,
      backupRetentionPeriod: 1,
      deletionProtection: false, // PoC 한정. production은 true 필수
    });
    neptuneCluster.addDependency(neptuneSubnetGroup);

    new neptune.CfnDBInstance(this, 'NeptuneInstance', {
      dbInstanceIdentifier: 'assembly-neptune-instance',
      dbInstanceClass: 'db.t3.medium',
      dbClusterIdentifier: neptuneCluster.ref,
    });

    this.neptuneClusterId = neptuneCluster.ref;
    this.neptuneEndpoint = neptuneCluster.attrEndpoint;

    // ─── OpenSearch Serverless ─────────────────────────────────────────────
    // Collection 생성 전 필수: encryption + network + data access security policy.
    // 순서 - encryption policy → network policy → collection → data access policy.
    const COLLECTION_NAME = 'assembly-dev-collection';

    const osEncryptionPolicy = new opensearchserverless.CfnSecurityPolicy(this, 'OsEncryptionPolicy', {
      name: 'assembly-dev-encrypt',
      type: 'encryption',
      description: 'AWS-managed KMS for assembly-dev-collection',
      policy: JSON.stringify({
        Rules: [{ ResourceType: 'collection', Resource: [`collection/${COLLECTION_NAME}`] }],
        AWSOwnedKey: true,
      }),
    });

    const osNetworkPolicy = new opensearchserverless.CfnSecurityPolicy(this, 'OsNetworkPolicy', {
      name: 'assembly-dev-network',
      type: 'network',
      description: 'Public dashboard + collection endpoint (dev). Production: VPC endpoint only.',
      policy: JSON.stringify([
        {
          Rules: [
            { ResourceType: 'collection', Resource: [`collection/${COLLECTION_NAME}`] },
            { ResourceType: 'dashboard', Resource: [`collection/${COLLECTION_NAME}`] },
          ],
          AllowFromPublic: true,
        },
      ]),
    });

    const osCollection = new opensearchserverless.CfnCollection(this, 'OsCollection', {
      name: COLLECTION_NAME,
      type: 'VECTORSEARCH',
      description: 'Assembly hybrid BM25(Nori) + KNN(Cohere embed-v4)',
    });
    osCollection.addDependency(osEncryptionPolicy);
    osCollection.addDependency(osNetworkPolicy);

    // Data access policy.
    //
    // ⚠️ 보안 trade-off (dev only): Principal이 account root.
    // - OpenSearch Serverless는 Principal 와일드카드를 미지원 ("Invalid request" 에러).
    //   참조: AWS Docs https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-data-access.html
    // - 따라서 narrow ARN 패턴(`role/prefix-*`) 사용 불가.
    // - Production 전환 시: compute stack의 task role ARN을 명시적으로 export →
    //   data stack이 cross-stack reference로 정확한 ARN 사용. cyclic dependency 회피
    //   위해 compute role을 별도 IamStack으로 분리하는 옵션 권장.
    //
    // Phase 5 polish 추적: docs/decisions/0007-opensearch-iam-tightening.md (작성 예정).
    new opensearchserverless.CfnAccessPolicy(this, 'OsDataAccessPolicy', {
      name: 'assembly-dev-access',
      type: 'data',
      description: 'Dev only: account root - Production은 명시적 task role ARN 사용 권장',
      policy: JSON.stringify([
        {
          Rules: [
            {
              ResourceType: 'collection',
              Resource: [`collection/${COLLECTION_NAME}`],
              Permission: ['aoss:DescribeCollectionItems', 'aoss:CreateCollectionItems', 'aoss:UpdateCollectionItems'],
            },
            {
              ResourceType: 'index',
              Resource: [`index/${COLLECTION_NAME}/*`],
              Permission: [
                'aoss:CreateIndex', 'aoss:DescribeIndex', 'aoss:ReadDocument',
                'aoss:WriteDocument', 'aoss:UpdateIndex', 'aoss:DeleteIndex',
              ],
            },
          ],
          Principal: [`arn:aws:iam::${this.account}:root`],
        },
      ]),
    });

    this.openSearchEndpoint = osCollection.attrCollectionEndpoint;

    // ─── DynamoDB 4개 ──────────────────────────────────────────────────────
    this.b2bKeysTable = new dynamodb.Table(this, 'B2bKeysTable', {
      tableName: 'ontology-assembly-dev-b2b-keys',
      partitionKey: { name: 'api_key_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: dynamodb.TableEncryption.AWS_MANAGED,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });
    this.adInventoryTable = new dynamodb.Table(this, 'AdInventoryTable', {
      tableName: 'ontology-assembly-dev-ad-inventory',
      partitionKey: { name: 'inventory_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: dynamodb.TableEncryption.AWS_MANAGED,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });
    this.adImpressionTable = new dynamodb.Table(this, 'AdImpressionTable', {
      tableName: 'ontology-assembly-dev-ad-impression',
      partitionKey: { name: 'impression_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: dynamodb.TableEncryption.AWS_MANAGED,
      removalPolicy: cdk.RemovalPolicy.DESTROY,    // ADR-0003 - 14일 TTL
      timeToLiveAttribute: 'ttl',
    });
    this.readerProfileTable = new dynamodb.Table(this, 'ReaderProfileTable', {
      tableName: 'ontology-assembly-dev-reader-profile',
      partitionKey: { name: 'reader_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: dynamodb.TableEncryption.AWS_MANAGED,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    new cdk.CfnOutput(this, 'NeptuneEndpoint', { value: this.neptuneEndpoint });
    new cdk.CfnOutput(this, 'OpenSearchEndpoint', { value: this.openSearchEndpoint });
  }
}
