#!/usr/bin/env node
/**
 * ontology-for-assembly CDK 앱 엔트리포인트.
 *
 * 6 스택 인스턴스화 + 의존성 wire-up:
 *   network → data → ai → compute → edge → observability
 *
 * gcc와 달리 신규 VPC 생성 (ADR-0001 D7).
 * Phase 1 인수 기준은 `cdk deploy --all`로 6 스택 모두 deploy + smoke.
 */
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { NetworkStack } from '../lib/network-stack';
import { DataStack } from '../lib/data-stack';
import { AiStack } from '../lib/ai-stack';
import { ComputeStack } from '../lib/compute-stack';
import { EdgeStack } from '../lib/edge-stack';
import { ObservabilityStack } from '../lib/observability-stack';

const app = new cdk.App();

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION ?? 'ap-northeast-2',
};

const envName = process.env.ASSEMBLY_ENV ?? 'dev';
const projectPrefix = `ontology-assembly-${envName}`;
const tags = { Project: 'ontology-for-assembly', Env: envName, ManagedBy: 'cdk' };

const network = new NetworkStack(app, `${projectPrefix}-network`, { env, tags });

// crossRegionReferences: true 는 producer + consumer 양쪽 모두 필요.
// Data는 b2bKeysTable, Compute는 alb를 us-east-1 EdgeStack에 export하므로 둘 다 활성화.
const data = new DataStack(app, `${projectPrefix}-data`, {
  env,
  tags,
  crossRegionReferences: true,
  vpc: network.vpc,
  appSg: network.appSg,
  neptuneSg: network.neptuneSg,
  osSg: network.osSg,
  lambdaSg: network.lambdaSg,
});

const ai = new AiStack(app, `${projectPrefix}-ai`, {
  env,
  tags,
  rawDocsBucket: data.rawDocsBucket,
});

const compute = new ComputeStack(app, `${projectPrefix}-compute`, {
  env,
  tags,
  crossRegionReferences: true,
  vpc: network.vpc,
  appSg: network.appSg,
  albSg: network.albSg,
  lambdaSg: network.lambdaSg,
  neptuneEndpoint: data.neptuneEndpoint,
  openSearchEndpoint: data.openSearchEndpoint,
  rawDocsBucket: data.rawDocsBucket,
  uploadsBucket: data.uploadsBucket,
  syntheticDataBucket: data.syntheticDataBucket,
  adInventoryTable: data.adInventoryTable,
  adImpressionTable: data.adImpressionTable,
  bedrockGuardrailId: ai.guardrailId,
  agentCoreMemoryId: ai.memoryId,
});

// VPC Origin은 cross-region 미지원 - edge stack을 ap-northeast-2(ALB와 동일)로 이전.
// us-east-1 요구사항(Lambda@Edge, ACM cert for CloudFront, WAFv2 CLOUDFRONT scope)은
// 현재 PoC에서 미사용 (Phase 5 polish 도입 시 별도 EdgeUsEast1Stack 분리).
const edge = new EdgeStack(app, `${projectPrefix}-edge`, {
  env,  // ap-northeast-2 - ALB와 동일 region (VPC Origin 요구사항)
  tags,
  alb: compute.alb,
  b2bKeysTable: data.b2bKeysTable,
  domainName: app.node.tryGetContext('domain') as string | undefined,
});

new ObservabilityStack(app, `${projectPrefix}-observability`, {
  env,
  tags,
  apiServiceArn: compute.apiServiceArn,
  webServiceArn: compute.webServiceArn,
  adMatcherFunctionArn: compute.adMatcherFunctionArn,
  neptuneClusterId: data.neptuneClusterId,
});

app.synth();
