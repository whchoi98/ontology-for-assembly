/**
 * AiStack - Bedrock Guardrails (정치 중립성) + KB + AgentCore Memory placeholders.
 *
 * 핵심:
 * - Bedrock Guardrails (ADR-0004 Layer 1): 정당 비방·정치인 모욕·차별 어휘 차단
 * - Bedrock Knowledge Base: RAG용 (시나리오 A·B·C)
 * - AgentCore Memory store: staff/subscriber/guest 3 namespace
 *
 * Note: Bedrock Guardrails CDK L1 construct는 안정화 중이라 일부는 CfnGuardrail 사용.
 */
import * as cdk from 'aws-cdk-lib';
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

export interface AiStackProps extends cdk.StackProps {
  rawDocsBucket: s3.IBucket;
}

export class AiStack extends cdk.Stack {
  public readonly guardrailId: string;
  public readonly guardrailArn: string;
  public readonly kbId: string;
  public readonly memoryId: string;

  constructor(scope: Construct, id: string, props: AiStackProps) {
    super(scope, id, props);

    // ─── Bedrock Guardrails (ADR-0004 Layer 1) ─────────────────────────────
    const guardrail = new bedrock.CfnGuardrail(this, 'PoliticalNeutralityGuardrail', {
      name: 'assembly-political-neutrality',
      description: 'ADR-0004 Layer 1: 정당 비방·정치인 모욕·이념 라벨 차단',
      blockedInputMessaging: '이 요청은 정치 중립성 가드레일에 의해 차단되었습니다.',
      blockedOutputsMessaging: '응답이 가드레일 정책에 의해 필터링되었습니다.',
      contentPolicyConfig: {
        filtersConfig: [
          { type: 'HATE', inputStrength: 'HIGH', outputStrength: 'HIGH' },
          { type: 'INSULTS', inputStrength: 'HIGH', outputStrength: 'HIGH' },
          { type: 'MISCONDUCT', inputStrength: 'MEDIUM', outputStrength: 'MEDIUM' },
        ],
      },
      topicPolicyConfig: {
        topicsConfig: [
          {
            name: 'PartyAttack',
            type: 'DENY',
            definition: '특정 정당에 대한 비방, 모욕, 일방적 가치 판단',
            examples: [
              '○○당은 무능하다',
              '○○당은 부패한 집단이다',
            ],
          },
          {
            name: 'PoliticianInsult',
            type: 'DENY',
            definition: '정치인 개인에 대한 인신공격, 모욕, 사적 영역 추론',
            examples: [
              '○○○ 의원은 쓰레기다',
              '○○○ 의원 가족이 ...',
            ],
          },
        ],
      },
      wordPolicyConfig: {
        managedWordListsConfig: [{ type: 'PROFANITY' }],
      },
    });

    this.guardrailId = guardrail.attrGuardrailId;
    this.guardrailArn = guardrail.attrGuardrailArn;

    // ─── Bedrock KB / AgentCore Memory placeholder ────────────────────────
    // Phase 1 PoC 단계에서는 환경변수로 ID 주입하는 패턴. CDK 자동 생성은
    // bedrock-agentcore가 GA되면 추가.
    this.kbId = process.env.BEDROCK_KB_ID ?? 'kb-not-configured';
    this.memoryId = process.env.AGENTCORE_MEMORY_ID ?? 'memory-not-configured';

    new cdk.CfnOutput(this, 'GuardrailId', { value: this.guardrailId });
    new cdk.CfnOutput(this, 'GuardrailArn', { value: this.guardrailArn });
  }
}
