/**
 * NetworkStack - 신규 VPC + 4 Security Group.
 *
 * ADR-0001 D7: gcc의 retail VPC import 패턴과 달리 assembly는 독립 VPC.
 * - VPC CIDR 10.30.0.0/16 (gcc 10.10.x / retail 10.20.x와 분리)
 * - 3-AZ, public + private(NAT) + isolated subnet
 * - 4 SG: app, alb, neptune, os, lambda(edge auth + ad matcher)
 *
 * ALB SG는 cloudfront prefix list만 ingress 허용 (ADR-0001 보안).
 */
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Construct } from 'constructs';

export class NetworkStack extends cdk.Stack {
  public readonly vpc: ec2.IVpc;
  public readonly albSg: ec2.SecurityGroup;
  public readonly appSg: ec2.SecurityGroup;
  public readonly neptuneSg: ec2.SecurityGroup;
  public readonly osSg: ec2.SecurityGroup;
  public readonly lambdaSg: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props: cdk.StackProps) {
    super(scope, id, props);

    // 신규 VPC - 3 AZ, NAT 1개 (PoC 비용 절감).
    this.vpc = new ec2.Vpc(this, 'Vpc', {
      vpcName: 'assembly-vpc',
      ipAddresses: ec2.IpAddresses.cidr('10.30.0.0/16'),
      maxAzs: 3,
      natGateways: 1,
      subnetConfiguration: [
        { name: 'public', subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        { name: 'private', subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, cidrMask: 24 },
        { name: 'isolated', subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
      ],
    });

    // ALB SG - CloudFront prefix list만 ingress
    this.albSg = new ec2.SecurityGroup(this, 'AlbSg', {
      vpc: this.vpc,
      securityGroupName: 'assembly-alb-sg',
      description: 'Assembly ALB - ingress from CloudFront prefix list only',
      allowAllOutbound: true,
    });
    const cfPrefixList = ec2.PrefixList.fromLookup(this, 'CloudFrontPrefixList', {
      prefixListName: 'com.amazonaws.global.cloudfront.origin-facing',
    });
    this.albSg.addIngressRule(
      ec2.Peer.prefixList(cfPrefixList.prefixListId),
      ec2.Port.tcp(80),
      'CloudFront origins HTTP',
    );

    // ECS app SG - ALB만 ingress
    this.appSg = new ec2.SecurityGroup(this, 'AppSg', {
      vpc: this.vpc,
      securityGroupName: 'assembly-app-sg',
      description: 'Assembly ECS Fargate app - ingress from ALB only',
      allowAllOutbound: true,
    });
    this.appSg.addIngressRule(this.albSg, ec2.Port.tcp(8080), 'ALB → API');
    this.appSg.addIngressRule(this.albSg, ec2.Port.tcp(3000), 'ALB → Web');

    // Neptune SG - app + lambda만 ingress (private)
    this.neptuneSg = new ec2.SecurityGroup(this, 'NeptuneSg', {
      vpc: this.vpc,
      securityGroupName: 'assembly-neptune-sg',
      description: 'Assembly Neptune - private, ECS/Lambda ingress only',
      allowAllOutbound: true,
    });
    this.neptuneSg.addIngressRule(this.appSg, ec2.Port.tcp(8182), 'API → Neptune');

    // OpenSearch SG
    this.osSg = new ec2.SecurityGroup(this, 'OsSg', {
      vpc: this.vpc,
      securityGroupName: 'assembly-os-sg',
      description: 'Assembly OpenSearch - VPC endpoint',
      allowAllOutbound: true,
    });
    this.osSg.addIngressRule(this.appSg, ec2.Port.tcp(443), 'API → OpenSearch');

    // Lambda SG (Ad Matcher + Lambda@Edge)
    this.lambdaSg = new ec2.SecurityGroup(this, 'LambdaSg', {
      vpc: this.vpc,
      securityGroupName: 'assembly-lambda-sg',
      description: 'Assembly Lambda - Ad Matcher + edge auth',
      allowAllOutbound: true,
    });
    this.neptuneSg.addIngressRule(this.lambdaSg, ec2.Port.tcp(8182), 'Lambda → Neptune');
    this.osSg.addIngressRule(this.lambdaSg, ec2.Port.tcp(443), 'Lambda → OpenSearch');

    new cdk.CfnOutput(this, 'VpcId', { value: this.vpc.vpcId });
  }
}
