/**
 * ComputeStack - ECS Fargate ARM64 (api + web) + ALB + Ad Matcher Lambda.
 *
 * ADR-0001: 모든 Fargate task는 ARM64 (Graviton). x86 이미지는 ECS reject.
 * ADR-0004 Layer 6: Ad Matcher는 별도 Lambda - API와 분리되어 광고 매칭 trace 독립.
 */
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import { Construct } from 'constructs';


// ─── 사전 빌드·푸시된 ECR 이미지 참조 ───────────────────────────────────
// 빌드: `docker buildx build --platform linux/arm64 -f api/Dockerfile -t <ecr>:<sha> --push .`
// SHA 갱신: 새 이미지 푸시 시 IMAGE_TAG 변경 + cdk deploy. `:latest`도 동시 push되므로 fallback.
const API_REPO_NAME = 'ontology-assembly-dev-api';
const WEB_REPO_NAME = 'ontology-assembly-dev-web';
// 환경 변수로 SHA 주입 가능 (CI 자동 배포). 미설정 시 :latest fallback.
const IMAGE_TAG = process.env.ASSEMBLY_IMAGE_TAG ?? 'latest';

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

    // ─── ALB (Private) ─────────────────────────────────────────────────────
    // 2024-11 GA CloudFront VPC Origin 사용 - ALB는 internal(private)로 유지.
    // CF가 PrivateLink로 직접 ALB ENI 접근. Public exposure 0.
    // 보안: SG ingress는 VPC CIDR로 좁힘 (network-stack.ts AlbSg).
    this.alb = new elbv2.ApplicationLoadBalancer(this, 'Alb', {
      vpc,
      internetFacing: false,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroup: albSg as ec2.SecurityGroup,
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
    // ECR 리포 reference - lookup으로 이미지 권한 자동 grant.
    const apiRepo = ecr.Repository.fromRepositoryName(this, 'ApiRepo', API_REPO_NAME);

    apiTaskDef.addContainer('api', {
      image: ecs.ContainerImage.fromEcrRepository(apiRepo, IMAGE_TAG),
      memoryLimitMiB: 1024,
      portMappings: [{ containerPort: 8080 }],
      environment: {
        AWS_REGION: this.region,
        ASSEMBLY_ENV: 'dev',
        // Demo 안전 모드 - boto3·외부 API 호출은 mock fixture. 라이브 시연 fail-safe.
        DEMO_PUBLIC_MODE: 'true',
        REQUIRE_ORIGIN_AUTH: 'false',
        NEPTUNE_ENDPOINT: neptuneEndpoint,
        OPENSEARCH_ENDPOINT: openSearchEndpoint,
        OPENSEARCH_INDEX: 'assembly-dev-kb-index',
        BEDROCK_CHAT_MODEL_ID: 'global.anthropic.claude-sonnet-4-6',
        BEDROCK_EMBED_MODEL_ID: 'global.cohere.embed-v4:0',
        BEDROCK_RERANKER_INFERENCE_PROFILE_ARN: 'arn:aws:bedrock:ap-northeast-2::reranker',
        BEDROCK_KB_ID: 'kb-not-configured',
        BEDROCK_GUARDRAIL_ID: bedrockGuardrailId,
        AGENTCORE_MEMORY_ID: agentCoreMemoryId,
        RAW_DOCS_BUCKET: rawDocsBucket.bucketName,
        UPLOADS_BUCKET: uploadsBucket.bucketName,
        SYNTHETIC_DATA_BUCKET: syntheticDataBucket.bucketName,
        // 외부 API key - DEMO_PUBLIC_MODE=true에선 미사용, 실 호출 시만 boto3로 fetch.
        ASSEMBLY_OPENAPI_KEY: 'demo-mode-via-secrets-manager',
        NAVER_NEWS_API_CLIENT_ID: 'demo-mode',
        NAVER_NEWS_API_CLIENT_SECRET: 'demo-mode',
        // Cognito - DEMO_PUBLIC_MODE에서 우회됨
        COGNITO_USER_POOL_ID: 'demo-mode',
        COGNITO_GUEST_IDENTITY_POOL_ID: 'demo-mode',
        COGNITO_APP_CLIENT_ID: 'demo-mode',
        ORIGIN_AUTH_SECRET_ARN: 'demo-mode',
        PUBLIC_DOMAIN: 'demo.cloudfront.net',
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
    const webRepo = ecr.Repository.fromRepositoryName(this, 'WebRepo', WEB_REPO_NAME);

    webTaskDef.addContainer('web', {
      image: ecs.ContainerImage.fromEcrRepository(webRepo, IMAGE_TAG),
      memoryLimitMiB: 512,
      portMappings: [{ containerPort: 3000 }],
      environment: {
        NEXT_PUBLIC_API_BASE_URL: '',  // 빈 값 = same origin (ALB가 라우팅)
      },
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
      // Next.js standalone build에는 /healthz 라우트 없음 - "/"는 항상 200 또는 307(redirect).
      // matcher를 2xx-3xx 범위로 두면 모든 정상 응답 허용.
      healthCheck: { path: '/', healthyHttpCodes: '200-399' },
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
