/**
 * NetworkStack - 공유 VPC import + 5 Security Group.
 *
 * 설계 변경 (2026-05-14): 신규 VPC 생성 to **gcc·retail·mfg 공유 VPC import**.
 * - VPC: cc-on-bedrock-vpc (vpc-0dfa5610180dfa628, 10.100.0.0/16)
 * - 2-AZ (ap-northeast-2a, 2b)
 * - 공유 NAT GW 2개 (시도별, public subnet 내)
 * - assembly 전용 SG 5개 신규: alb, app, neptune, os, lambda
 *
 * 이유:
 * - 4개 ontology 프로젝트(gcc·retail·mfg·assembly)가 같은 VPC 공유 to NAT GW 단가 비용 절감
 * - 동일 NAT GW 사용으로 외부 API rate-limit 추적 단일화
 * - 4개 stack 간 cross-VPC traffic 없음 (assembly가 다른 ontology 데이터 참조 안 함)
 *
 * 변경 시 ADR-0006 (VPC 공유 이전 결정) 참조.
 */
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Construct } from 'constructs';


// ─── 공유 VPC 메타 (cc-on-bedrock-vpc) ──────────────────────────────────────
// gcc·retail·mfg와 동일 VPC. 변경 시 모든 프로젝트 영향. 신중히.
export const SHARED_VPC_ID = 'vpc-0dfa5610180dfa628';
export const SHARED_VPC_CIDR = '10.100.0.0/16';

export const SHARED_AZS = ['ap-northeast-2a', 'ap-northeast-2b'] as const;

// Public subnets (2 AZ). ALB가 거주.
export const SHARED_PUBLIC_SUBNETS = [
  { subnetId: 'subnet-08486a1e618b1991e', az: 'ap-northeast-2a' },  // 10.100.0.0/24
  { subnetId: 'subnet-0c161777c4031c320', az: 'ap-northeast-2b' },  // 10.100.1.0/24
] as const;

// Private with NAT egress (2 AZ). ECS Fargate + Lambda 거주.
export const SHARED_PRIVATE_SUBNETS = [
  { subnetId: 'subnet-07b1e65682847dce9', az: 'ap-northeast-2a' },  // 10.100.16.0/20
  { subnetId: 'subnet-095297380cd45e1eb', az: 'ap-northeast-2b' },  // 10.100.32.0/20
] as const;

// Isolated subnets (2 AZ). Neptune + RDS 거주 (egress 없음).
export const SHARED_ISOLATED_SUBNETS = [
  { subnetId: 'subnet-022000a208af56aae', az: 'ap-northeast-2a' },  // 10.100.48.0/23
  { subnetId: 'subnet-01b8fb3c462210113', az: 'ap-northeast-2b' },  // 10.100.50.0/23
] as const;


export class NetworkStack extends cdk.Stack {
  public readonly vpc: ec2.IVpc;
  public readonly albSg: ec2.SecurityGroup;
  public readonly appSg: ec2.SecurityGroup;
  public readonly neptuneSg: ec2.SecurityGroup;
  public readonly osSg: ec2.SecurityGroup;
  public readonly lambdaSg: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props: cdk.StackProps) {
    super(scope, id, props);

    // ─── 공유 VPC import (cc-on-bedrock-vpc) ──────────────────────────
    this.vpc = ec2.Vpc.fromVpcAttributes(this, 'SharedVpc', {
      vpcId: SHARED_VPC_ID,
      vpcCidrBlock: SHARED_VPC_CIDR,
      availabilityZones: [...SHARED_AZS],
      publicSubnetIds: SHARED_PUBLIC_SUBNETS.map((s) => s.subnetId),
      publicSubnetRouteTableIds: SHARED_PUBLIC_SUBNETS.map(
        (_, i) => `rtb-public-${i}`, // CDK는 lookup으로 가져오지 않으면 plaholder 필요. ALB는 public subnet만 사용 to 동작 영향 없음.
      ),
      privateSubnetIds: SHARED_PRIVATE_SUBNETS.map((s) => s.subnetId),
      privateSubnetRouteTableIds: SHARED_PRIVATE_SUBNETS.map((_, i) => `rtb-private-${i}`),
      isolatedSubnetIds: SHARED_ISOLATED_SUBNETS.map((s) => s.subnetId),
      isolatedSubnetRouteTableIds: SHARED_ISOLATED_SUBNETS.map((_, i) => `rtb-isolated-${i}`),
    });

    // ALB SG.
    // 설계 변경 (2026-05-15): CloudFront VPC Origin 아키텍처로 전환.
    // - VPC Origin은 PrivateLink 기반 - public IP 노출 0. AWS-managed prefix list 미사용.
    // - ENI는 같은 VPC(10.100.0.0/16) 안에서 동적 생성되므로 CIDR 단순 매칭.
    // - SG name/description은 immutable이라 원래 값 유지 (replacement 회피).
    this.albSg = new ec2.SecurityGroup(this, 'AlbSg', {
      vpc: this.vpc,
      securityGroupName: 'assembly-alb-sg',
      description: 'Assembly ALB - ingress from CloudFront prefix list only',
      allowAllOutbound: true,
    });
    this.albSg.addIngressRule(
      ec2.Peer.ipv4(SHARED_VPC_CIDR),
      ec2.Port.tcp(80),
      'CloudFront VPC Origin ENI (private)',
    );

    // ECS app SG - ALB만 ingress
    this.appSg = new ec2.SecurityGroup(this, 'AppSg', {
      vpc: this.vpc,
      securityGroupName: 'assembly-app-sg',
      description: 'Assembly ECS Fargate app - ingress from ALB only',
      allowAllOutbound: true,
    });
    this.appSg.addIngressRule(this.albSg, ec2.Port.tcp(8080), 'ALB to API');
    this.appSg.addIngressRule(this.albSg, ec2.Port.tcp(3000), 'ALB to Web');

    // Neptune SG - app + lambda만 ingress (isolated subnet 거주)
    this.neptuneSg = new ec2.SecurityGroup(this, 'NeptuneSg', {
      vpc: this.vpc,
      securityGroupName: 'assembly-neptune-sg',
      description: 'Assembly Neptune - isolated, ECS/Lambda ingress only',
      allowAllOutbound: true,
    });
    this.neptuneSg.addIngressRule(this.appSg, ec2.Port.tcp(8182), 'API to Neptune');

    // OpenSearch SG
    this.osSg = new ec2.SecurityGroup(this, 'OsSg', {
      vpc: this.vpc,
      securityGroupName: 'assembly-os-sg',
      description: 'Assembly OpenSearch - VPC endpoint',
      allowAllOutbound: true,
    });
    this.osSg.addIngressRule(this.appSg, ec2.Port.tcp(443), 'API to OpenSearch');

    // Lambda SG (Ad Matcher + Lambda@Edge)
    this.lambdaSg = new ec2.SecurityGroup(this, 'LambdaSg', {
      vpc: this.vpc,
      securityGroupName: 'assembly-lambda-sg',
      description: 'Assembly Lambda - Ad Matcher + edge auth',
      allowAllOutbound: true,
    });
    this.neptuneSg.addIngressRule(this.lambdaSg, ec2.Port.tcp(8182), 'Lambda to Neptune');
    this.osSg.addIngressRule(this.lambdaSg, ec2.Port.tcp(443), 'Lambda to OpenSearch');

    new cdk.CfnOutput(this, 'VpcId', { value: this.vpc.vpcId, description: '공유 VPC ID (cc-on-bedrock-vpc)' });
    new cdk.CfnOutput(this, 'SharedNatGateways', {
      value: 'nat-00b8a70dc184a4d0c (AZ-a), nat-08379e076e2e6e234 (AZ-b)',
      description: 'gcc·retail·mfg와 공유',
    });
  }
}
