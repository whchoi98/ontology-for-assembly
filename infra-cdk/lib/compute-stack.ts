/**
 * ComputeStack - ECS Fargate ARM64 (api + web) + ALB + Ad Matcher Lambda.
 *
 * ADR-0001: 모든 Fargate task는 ARM64 (Graviton). x86 이미지는 ECS reject.
 * ADR-0004 Layer 6: Ad Matcher는 별도 Lambda - API와 분리되어 광고 매칭 trace 독립.
 */
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import { Construct } from 'constructs';

export interface ComputeStackProps extends cdk.StackProps {
  vpc: ec2.IVpc;
  appSg: ec2.ISecurityGroup;
  albSg: ec2.ISecurityGroup;
  lambdaSg: ec2.ISecurityGroup;
  neptuneEndpoint: string;
  openSearchEndpoint: string;
  rawDocsBucket: s3.IBucket;
  uploadsBucket: s3.IBucket;
  syntheticDataBucket: s3.IBucket;
  adInventoryTable: dynamodb.ITable;
  adImpressionTable: dynamodb.ITable;
  bedrockGuardrailId: string;
  agentCoreMemoryId: string;
}

export class ComputeStack extends cdk.Stack {
  public readonly alb: elbv2.ApplicationLoadBalancer;
  public readonly apiServiceArn: string;
  public readonly webServiceArn: string;
  public readonly adMatcherFunctionArn: string;

  constructor(scope: Construct, id: string, props: ComputeStackProps) {
    super(scope, id, props);

    const {
      vpc, appSg, albSg, lambdaSg,
      neptuneEndpoint, openSearchEndpoint,
      rawDocsBucket, uploadsBucket, syntheticDataBucket,
      adInventoryTable, adImpressionTable,
      bedrockGuardrailId, agentCoreMemoryId,
    } = props;

    // ─── ECS cluster ───────────────────────────────────────────────────────
    const cluster = new ecs.Cluster(this, 'Cluster', {
      vpc,
      clusterName: 'assembly-dev-cluster',
      containerInsights: true,
    });

    // ─── ALB ───────────────────────────────────────────────────────────────
    this.alb = new elbv2.ApplicationLoadBalancer(this, 'Alb', {
      vpc,
      internetFacing: false,
      securityGroup: albSg as ec2.SecurityGroup,
      loadBalancerName: 'assembly-dev-alb',
    });
    const listener = this.alb.addListener('Listener', {
      port: 80,
      // 기본 응답 - api / web 패턴 라우팅 외 모든 요청은 503.
      defaultAction: elbv2.ListenerAction.fixedResponse(503, {
        contentType: 'text/plain',
        messageBody: 'service unavailable',
      }),
    });

    // ─── Task IAM Role (Bedrock + Neptune + OS + S3 + DDB) ────────────────
    const apiTaskRole = new iam.Role(this, 'ApiTaskRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      description: 'Assembly API Fargate task role',
    });
    apiTaskRole.addToPolicy(new iam.PolicyStatement({
      actions: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream',
                'bedrock:ApplyGuardrail'],
      resources: ['*'],     // model ARN은 cross-region inference profile - 좁힐 수 있을 때 좁히기
    }));
    apiTaskRole.addToPolicy(new iam.PolicyStatement({
      actions: ['neptune-db:*'],
      resources: [`arn:aws:neptune-db:${this.region}:${this.account}:*/*`],
    }));
    apiTaskRole.addToPolicy(new iam.PolicyStatement({
      actions: ['aoss:APIAccessAll'],
      resources: ['*'],
    }));
    rawDocsBucket.grantRead(apiTaskRole);
    uploadsBucket.grantReadWrite(apiTaskRole);
    syntheticDataBucket.grantRead(apiTaskRole);

    // ─── API task definition (ARM64) ───────────────────────────────────────
    const apiTaskDef = new ecs.FargateTaskDefinition(this, 'ApiTaskDef', {
      cpu: 1024,
      memoryLimitMiB: 2048,
      runtimePlatform: {
        cpuArchitecture: ecs.CpuArchitecture.ARM64,
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
      },
      taskRole: apiTaskRole,
    });
    apiTaskDef.addContainer('api', {
      // 첫 deploy는 placeholder image (ECR push 후 force-new-deployment)
      image: ecs.ContainerImage.fromRegistry('public.ecr.aws/docker/library/nginx:alpine'),
      memoryLimitMiB: 1024,
      portMappings: [{ containerPort: 8080 }],
      environment: {
        AWS_REGION: this.region,
        ASSEMBLY_ENV: 'dev',
        NEPTUNE_ENDPOINT: neptuneEndpoint,
        OPENSEARCH_ENDPOINT: openSearchEndpoint,
        BEDROCK_CHAT_MODEL_ID: 'global.anthropic.claude-sonnet-4-6',
        BEDROCK_EMBED_MODEL_ID: 'global.cohere.embed-v4:0',
        BEDROCK_GUARDRAIL_ID: bedrockGuardrailId,
        AGENTCORE_MEMORY_ID: agentCoreMemoryId,
        RAW_DOCS_BUCKET: rawDocsBucket.bucketName,
        UPLOADS_BUCKET: uploadsBucket.bucketName,
        SYNTHETIC_DATA_BUCKET: syntheticDataBucket.bucketName,
      },
      logging: ecs.LogDriver.awsLogs({
        streamPrefix: 'assembly-api',
        logRetention: logs.RetentionDays.TWO_WEEKS,
      }),
    });

    const apiService = new ecs.FargateService(this, 'ApiService', {
      cluster,
      taskDefinition: apiTaskDef,
      desiredCount: 2,
      serviceName: 'assembly-dev-api',
      securityGroups: [appSg as ec2.SecurityGroup],
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
    });

    listener.addTargets('ApiTarget', {
      port: 8080,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targets: [apiService],
      healthCheck: { path: '/api/healthz', healthyHttpCodes: '200' },
      conditions: [elbv2.ListenerCondition.pathPatterns(['/api/*'])],
      priority: 10,
    });

    this.apiServiceArn = apiService.serviceArn;

    // ─── Web task (Next.js) ───────────────────────────────────────────────
    const webTaskDef = new ecs.FargateTaskDefinition(this, 'WebTaskDef', {
      cpu: 512,
      memoryLimitMiB: 1024,
      runtimePlatform: {
        cpuArchitecture: ecs.CpuArchitecture.ARM64,
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
      },
    });
    webTaskDef.addContainer('web', {
      image: ecs.ContainerImage.fromRegistry('public.ecr.aws/docker/library/nginx:alpine'),
      memoryLimitMiB: 512,
      portMappings: [{ containerPort: 3000 }],
      logging: ecs.LogDriver.awsLogs({
        streamPrefix: 'assembly-web',
        logRetention: logs.RetentionDays.TWO_WEEKS,
      }),
    });

    const webService = new ecs.FargateService(this, 'WebService', {
      cluster,
      taskDefinition: webTaskDef,
      desiredCount: 2,
      serviceName: 'assembly-dev-web',
      securityGroups: [appSg as ec2.SecurityGroup],
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
    });

    listener.addTargets('WebTarget', {
      port: 3000,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targets: [webService],
      healthCheck: { path: '/healthz', healthyHttpCodes: '200,307' },
      conditions: [elbv2.ListenerCondition.pathPatterns(['/*'])],
      priority: 100, // api priority 10이 우선, 나머지 web
    });

    this.webServiceArn = webService.serviceArn;

    // ─── Ad Matcher Lambda (ADR-0004 Layer 6) ──────────────────────────────
    const adMatcherRole = new iam.Role(this, 'AdMatcherRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaVPCAccessExecutionRole'),
      ],
    });
    adMatcherRole.addToPolicy(new iam.PolicyStatement({
      actions: ['bedrock:InvokeModel', 'bedrock:ApplyGuardrail'],
      resources: ['*'],
    }));
    adInventoryTable.grantReadData(adMatcherRole);
    adImpressionTable.grantReadWriteData(adMatcherRole);

    const adMatcher = new lambda.Function(this, 'AdMatcherFunction', {
      functionName: 'assembly-dev-ad-matcher',
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.lambda_handler',
      // Inline placeholder - 실제 코드는 후속 deploy
      code: lambda.Code.fromInline(
        'def lambda_handler(event, context):\n' +
        '    return {"statusCode": 200, "body": "ad-matcher placeholder"}\n',
      ),
      role: adMatcherRole,
      timeout: cdk.Duration.seconds(30),
      memorySize: 512,
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroups: [lambdaSg as ec2.SecurityGroup],
      environment: {
        AD_INVENTORY_TABLE: adInventoryTable.tableName,
        AD_IMPRESSION_TABLE: adImpressionTable.tableName,
        BEDROCK_GUARDRAIL_ID: bedrockGuardrailId,
      },
    });
    this.adMatcherFunctionArn = adMatcher.functionArn;

    new cdk.CfnOutput(this, 'AlbDnsName', { value: this.alb.loadBalancerDnsName });
  }
}
