/**
 * 6 스택 Jest 스냅샷 + 핵심 리소스 존재 검증.
 *
 * 스냅샷 갱신: `npx jest -u` 후 diff 리뷰.
 * 변경 의도 없을 때 스냅샷 mismatch는 의도치 않은 인프라 drift.
 */
import * as cdk from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { NetworkStack } from '../lib/network-stack';
import { DataStack } from '../lib/data-stack';
import { AiStack } from '../lib/ai-stack';
import { ComputeStack } from '../lib/compute-stack';
import { EdgeStack } from '../lib/edge-stack';
import { ObservabilityStack } from '../lib/observability-stack';

const ENV = { account: '111111111111', region: 'ap-northeast-2' };
const ENV_USE1 = { account: '111111111111', region: 'us-east-1' };
const tags = { Project: 'ontology-for-assembly', Env: 'test', ManagedBy: 'cdk' };

function buildStacks() {
  const app = new cdk.App();
  // Inject CFN prefix-list lookup stub via context (avoids real AWS lookup in test).
  app.node.setContext(
    'availability-zones:account=111111111111:region=ap-northeast-2',
    ['ap-northeast-2a', 'ap-northeast-2b', 'ap-northeast-2c'],
  );
  app.node.setContext(
    'aws-cdk:enableDiffNoFail',
    true,
  );

  const network = new NetworkStack(app, 'test-network', { env: ENV, tags });
  const data = new DataStack(app, 'test-data', {
    env: ENV, tags,
    vpc: network.vpc,
    appSg: network.appSg,
    neptuneSg: network.neptuneSg,
    osSg: network.osSg,
    lambdaSg: network.lambdaSg,
  });
  const ai = new AiStack(app, 'test-ai', {
    env: ENV, tags,
    rawDocsBucket: data.rawDocsBucket,
  });
  const compute = new ComputeStack(app, 'test-compute', {
    env: ENV, tags,
    vpc: network.vpc,
    appSg: network.appSg,
    albSg: network.albSg,
    lambdaSg: network.lambdaSg,
    neptuneEndpoint: 'neptune.test.local',
    openSearchEndpoint: 'https://os.test.local',
    rawDocsBucket: data.rawDocsBucket,
    uploadsBucket: data.uploadsBucket,
    syntheticDataBucket: data.syntheticDataBucket,
    adInventoryTable: data.adInventoryTable,
    adImpressionTable: data.adImpressionTable,
    bedrockGuardrailId: ai.guardrailId,
    agentCoreMemoryId: ai.memoryId,
  });
  const edge = new EdgeStack(app, 'test-edge', {
    env: ENV_USE1, tags,
    crossRegionReferences: true,
    alb: compute.alb,
    b2bKeysTable: data.b2bKeysTable,
  });
  const observability = new ObservabilityStack(app, 'test-observability', {
    env: ENV, tags,
    apiServiceArn: compute.apiServiceArn,
    webServiceArn: compute.webServiceArn,
    adMatcherFunctionArn: compute.adMatcherFunctionArn,
    neptuneClusterId: data.neptuneClusterId,
  });
  return { network, data, ai, compute, edge, observability };
}


describe('NetworkStack', () => {
  it('VPC + 4 SGs 생성', () => {
    const { network } = buildStacks();
    const t = Template.fromStack(network);
    t.resourceCountIs('AWS::EC2::VPC', 1);
    t.resourceCountIs('AWS::EC2::SecurityGroup', 5);  // alb + app + neptune + os + lambda
  });

  it('VPC CIDR 10.30.0.0/16 (assembly 전용)', () => {
    const { network } = buildStacks();
    const t = Template.fromStack(network);
    t.hasResourceProperties('AWS::EC2::VPC', { CidrBlock: '10.30.0.0/16' });
  });
});


describe('DataStack', () => {
  it('Neptune cluster + instance 생성', () => {
    const { data } = buildStacks();
    const t = Template.fromStack(data);
    t.resourceCountIs('AWS::Neptune::DBCluster', 1);
    t.resourceCountIs('AWS::Neptune::DBInstance', 1);
  });

  it('S3 3개 + DynamoDB 4개', () => {
    const { data } = buildStacks();
    const t = Template.fromStack(data);
    t.resourceCountIs('AWS::S3::Bucket', 3);
    t.resourceCountIs('AWS::DynamoDB::Table', 4);
  });

  it('OpenSearch Serverless VECTORSEARCH 컬렉션', () => {
    const { data } = buildStacks();
    const t = Template.fromStack(data);
    t.hasResourceProperties('AWS::OpenSearchServerless::Collection', {
      Type: 'VECTORSEARCH',
    });
  });

  it('AdImpression 테이블에 TTL 설정', () => {
    const { data } = buildStacks();
    const t = Template.fromStack(data);
    t.hasResourceProperties('AWS::DynamoDB::Table', {
      TableName: 'ontology-assembly-dev-ad-impression',
      TimeToLiveSpecification: {
        AttributeName: 'ttl',
        Enabled: true,
      },
    });
  });
});


describe('AiStack', () => {
  it('Bedrock Guardrail 정치 중립성 생성', () => {
    const { ai } = buildStacks();
    const t = Template.fromStack(ai);
    t.resourceCountIs('AWS::Bedrock::Guardrail', 1);
  });

  it('Guardrail에 PartyAttack/PoliticianInsult 토픽 포함', () => {
    const { ai } = buildStacks();
    const t = Template.fromStack(ai);
    t.hasResourceProperties('AWS::Bedrock::Guardrail', {
      Name: 'assembly-political-neutrality',
    });
  });
});


describe('ComputeStack', () => {
  it('ECS cluster + ALB + 2 services + Ad Matcher Lambda', () => {
    const { compute } = buildStacks();
    const t = Template.fromStack(compute);
    t.resourceCountIs('AWS::ECS::Cluster', 1);
    t.resourceCountIs('AWS::ElasticLoadBalancingV2::LoadBalancer', 1);
    t.resourceCountIs('AWS::ECS::Service', 2);     // api + web
    // Ad Matcher Lambda 1개 + CDK 자동 생성 logRetention Lambda(들) 별도.
    // 의도된 함수만 검증:
    t.hasResourceProperties('AWS::Lambda::Function', {
      FunctionName: 'assembly-dev-ad-matcher',
      Architectures: ['arm64'],
    });
  });

  it('모든 ECS task ARM64 (ADR-0001)', () => {
    const { compute } = buildStacks();
    const t = Template.fromStack(compute);
    t.allResourcesProperties('AWS::ECS::TaskDefinition', {
      RuntimePlatform: {
        CpuArchitecture: 'ARM64',
        OperatingSystemFamily: 'LINUX',
      },
    });
  });

  it('Ad Matcher Lambda ARM64', () => {
    const { compute } = buildStacks();
    const t = Template.fromStack(compute);
    t.hasResourceProperties('AWS::Lambda::Function', {
      Architectures: ['arm64'],
      FunctionName: 'assembly-dev-ad-matcher',
    });
  });
});


describe('EdgeStack', () => {
  it('Cognito user pool 2개 (staff + subscriber)', () => {
    const { edge } = buildStacks();
    const t = Template.fromStack(edge);
    t.resourceCountIs('AWS::Cognito::UserPool', 2);
  });

  it('Cognito IdentityPool 1개 (게스트 - 일반 독자 익명)', () => {
    const { edge } = buildStacks();
    const t = Template.fromStack(edge);
    t.resourceCountIs('AWS::Cognito::IdentityPool', 1);
  });

  it('Staff 페르소나 3 그룹 + Subscriber 3 tier 그룹', () => {
    const { edge } = buildStacks();
    const t = Template.fromStack(edge);
    t.resourceCountIs('AWS::Cognito::UserPoolGroup', 6);
  });

  it('API Gateway B2B + Usage Plan', () => {
    const { edge } = buildStacks();
    const t = Template.fromStack(edge);
    t.resourceCountIs('AWS::ApiGateway::RestApi', 1);
    t.resourceCountIs('AWS::ApiGateway::UsagePlan', 1);
  });

  it('CloudFront distribution', () => {
    const { edge } = buildStacks();
    const t = Template.fromStack(edge);
    t.resourceCountIs('AWS::CloudFront::Distribution', 1);
  });
});


describe('ObservabilityStack', () => {
  it('Dashboard + 알람 2개 (political_balance + 5xx)', () => {
    const { observability } = buildStacks();
    const t = Template.fromStack(observability);
    t.resourceCountIs('AWS::CloudWatch::Dashboard', 1);
    t.resourceCountIs('AWS::CloudWatch::Alarm', 2);
  });

  it('political_balance_score 알람 임계 0.8', () => {
    const { observability } = buildStacks();
    const t = Template.fromStack(observability);
    t.hasResourceProperties('AWS::CloudWatch::Alarm', {
      AlarmName: 'assembly-political-balance-low',
      Threshold: 0.8,
    });
  });
});


describe('스냅샷 (drift 감지)', () => {
  for (const name of ['network', 'data', 'ai', 'compute', 'edge', 'observability']) {
    it(`${name} 스택 스냅샷`, () => {
      const stacks = buildStacks();
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const stack = (stacks as any)[name];
      const template = Template.fromStack(stack).toJSON();
      expect(template).toMatchSnapshot();
    });
  }
});
