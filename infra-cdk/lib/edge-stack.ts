/**
 * EdgeStack - CloudFront + Cognito 3 pool + API Gateway B2B + Lambda@Edge.
 *
 * us-east-1 deploy (Lambda@Edge + CloudFront ACM 요구사항).
 * ADR-0003: 3 인증 시스템 분리 - staff / subscriber / guest + B2B API Gateway.
 *
 * 첫 deploy는 `*.cloudfront.net` URL. 커스텀 도메인은 `-c domain=...` context로.
 */
import * as cdk from 'aws-cdk-lib';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import { Construct } from 'constructs';

export interface EdgeStackProps extends cdk.StackProps {
  alb: elbv2.IApplicationLoadBalancer;
  b2bKeysTable: dynamodb.ITable;
  domainName?: string;
}

export class EdgeStack extends cdk.Stack {
  public readonly distribution: cloudfront.IDistribution;
  public readonly staffUserPool: cognito.IUserPool;
  public readonly subscriberUserPool: cognito.IUserPool;
  public readonly guestIdentityPoolRef: string;
  public readonly b2bApiId: string;

  constructor(scope: Construct, id: string, props: EdgeStackProps) {
    super(scope, id, props);

    const { alb, b2bKeysTable } = props;

    // ─── Cognito #1 — Staff user pool ──────────────────────────────────────
    this.staffUserPool = new cognito.UserPool(this, 'StaffUserPool', {
      userPoolName: 'assembly-staff-pool',
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      passwordPolicy: {
        minLength: 12,
        requireUppercase: true,
        requireLowercase: true,
        requireDigits: true,
        requireSymbols: true,
      },
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });
    new cognito.CfnUserPoolGroup(this, 'EditorialGroup', {
      userPoolId: this.staffUserPool.userPoolId,
      groupName: 'editorial',
    });
    new cognito.CfnUserPoolGroup(this, 'DataAiGroup', {
      userPoolId: this.staffUserPool.userPoolId,
      groupName: 'data_ai',
    });
    new cognito.CfnUserPoolGroup(this, 'AdSalesGroup', {
      userPoolId: this.staffUserPool.userPoolId,
      groupName: 'ad_sales',
    });

    // ─── Cognito #2 — Subscriber user pool ─────────────────────────────────
    this.subscriberUserPool = new cognito.UserPool(this, 'SubscriberUserPool', {
      userPoolName: 'assembly-subscriber-pool',
      selfSignUpEnabled: true,
      signInAliases: { email: true },
      passwordPolicy: { minLength: 10 },
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });
    new cognito.CfnUserPoolGroup(this, 'TierFree', {
      userPoolId: this.subscriberUserPool.userPoolId,
      groupName: 'free',
    });
    new cognito.CfnUserPoolGroup(this, 'TierStandard', {
      userPoolId: this.subscriberUserPool.userPoolId,
      groupName: 'standard',
    });
    new cognito.CfnUserPoolGroup(this, 'TierPremium', {
      userPoolId: this.subscriberUserPool.userPoolId,
      groupName: 'premium',
    });

    // ─── Cognito #3 — Guest Identity Pool (일반 독자 익명) ─────────────────
    const guestIdentityPool = new cognito.CfnIdentityPool(this, 'GuestIdentityPool', {
      identityPoolName: 'assembly-guest-pool',
      allowUnauthenticatedIdentities: true,
    });
    this.guestIdentityPoolRef = guestIdentityPool.ref;

    // ─── API Gateway B2B (별도 도메인) ─────────────────────────────────────
    const b2bApi = new apigateway.RestApi(this, 'B2bApi', {
      restApiName: 'assembly-b2b-api',
      description: 'B2B 정책 인텔리전스 API - 페르소나 b2b',
      apiKeySourceType: apigateway.ApiKeySourceType.HEADER,
      deployOptions: {
        stageName: 'v1',
        throttlingBurstLimit: 200,
        throttlingRateLimit: 100,
      },
    });
    // Placeholder healthz endpoint - 실제 라우트는 후속 deploy에서 ALB 또는 Lambda 통합으로 추가.
    // CDK 검증상 REST API는 1개 이상 메서드 필요.
    b2bApi.root.addResource('healthz').addMethod(
      'GET',
      new apigateway.MockIntegration({
        integrationResponses: [{ statusCode: '200',
          responseTemplates: { 'application/json': '{"status":"ok"}' } }],
        requestTemplates: { 'application/json': '{"statusCode":200}' },
      }),
      { methodResponses: [{ statusCode: '200' }] },
    );
    const usagePlan = b2bApi.addUsagePlan('DefaultPlan', {
      name: 'assembly-b2b-default',
      throttle: { burstLimit: 100, rateLimit: 50 },
      quota: { limit: 100000, period: apigateway.Period.MONTH },
    });
    usagePlan.addApiStage({ stage: b2bApi.deploymentStage });
    this.b2bApiId = b2bApi.restApiId;

    // ─── CloudFront (B2C web + API) - VPC Origin ──────────────────────────
    // 2024-11 GA: CloudFront가 internal ALB에 PrivateLink로 직접 접근.
    // Public ALB·prefix list 모두 불필요. ALB는 private subnet 안.
    this.distribution = new cloudfront.Distribution(this, 'Distribution', {
      comment: 'Assembly B2C/staff distribution (VPC origin)',
      defaultBehavior: {
        origin: origins.VpcOrigin.withApplicationLoadBalancer(alb, {
          protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
          httpPort: 80,
        }),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
        cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
        originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
      },
      priceClass: cloudfront.PriceClass.PRICE_CLASS_200,
    });

    new cdk.CfnOutput(this, 'DistributionDomainName', {
      value: this.distribution.distributionDomainName,
    });
    new cdk.CfnOutput(this, 'StaffUserPoolId', { value: this.staffUserPool.userPoolId });
    new cdk.CfnOutput(this, 'SubscriberUserPoolId', {
      value: this.subscriberUserPool.userPoolId,
    });
    new cdk.CfnOutput(this, 'B2bApiUrl', { value: b2bApi.url });
  }
}
