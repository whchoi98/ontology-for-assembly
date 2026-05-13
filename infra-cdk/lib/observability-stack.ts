/**
 * ObservabilityStack - CloudWatch dashboard + alarms.
 *
 * 핵심 메트릭:
 * - ECS api/web service health
 * - Ad Matcher Lambda 호출·에러
 * - Neptune CPU·연결
 * - political_balance_score 메트릭 (api에서 PutMetricData)
 */
import * as cdk from 'aws-cdk-lib';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import { Construct } from 'constructs';

export interface ObservabilityStackProps extends cdk.StackProps {
  apiServiceArn: string;
  webServiceArn: string;
  adMatcherFunctionArn: string;
  neptuneClusterId: string;
}

export class ObservabilityStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: ObservabilityStackProps) {
    super(scope, id, props);

    const dashboard = new cloudwatch.Dashboard(this, 'Dashboard', {
      dashboardName: 'assembly-dev-dashboard',
      defaultInterval: cdk.Duration.minutes(15),
    });

    // ECS 서비스 헬스
    dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'ECS Service - CPU/Memory',
        left: [
          new cloudwatch.Metric({
            namespace: 'AWS/ECS',
            metricName: 'CPUUtilization',
            statistic: 'Average',
          }),
        ],
        right: [
          new cloudwatch.Metric({
            namespace: 'AWS/ECS',
            metricName: 'MemoryUtilization',
            statistic: 'Average',
          }),
        ],
        width: 24,
      }),
    );

    // Ad Matcher Lambda
    dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'Ad Matcher Lambda - invocations / errors',
        left: [
          new cloudwatch.Metric({
            namespace: 'AWS/Lambda',
            metricName: 'Invocations',
            statistic: 'Sum',
            dimensionsMap: { FunctionName: 'assembly-dev-ad-matcher' },
          }),
        ],
        right: [
          new cloudwatch.Metric({
            namespace: 'AWS/Lambda',
            metricName: 'Errors',
            statistic: 'Sum',
            dimensionsMap: { FunctionName: 'assembly-dev-ad-matcher' },
          }),
        ],
        width: 24,
      }),
    );

    // ─── Alarms ────────────────────────────────────────────────────────────

    // 정치 균형 점수 평균 < 0.8 시 알람 (api에서 PutMetricData로 게시)
    new cloudwatch.Alarm(this, 'LowBalanceScoreAlarm', {
      alarmName: 'assembly-political-balance-low',
      alarmDescription: 'political_balance_score 평균이 ALARM_THRESHOLD(0.8) 미만',
      metric: new cloudwatch.Metric({
        namespace: 'Assembly/Guardrails',
        metricName: 'political_balance_score',
        statistic: 'Average',
        period: cdk.Duration.minutes(15),
      }),
      threshold: 0.8,
      comparisonOperator: cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
      evaluationPeriods: 2,
      datapointsToAlarm: 2,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });

    // ECS 5xx 에러율
    new cloudwatch.Alarm(this, 'AlbHttp5xxAlarm', {
      alarmName: 'assembly-alb-5xx-high',
      alarmDescription: 'ALB 5xx 비율 > 1%',
      metric: new cloudwatch.Metric({
        namespace: 'AWS/ApplicationELB',
        metricName: 'HTTPCode_Target_5XX_Count',
        statistic: 'Sum',
        period: cdk.Duration.minutes(5),
      }),
      threshold: 10,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
      evaluationPeriods: 2,
    });

    new cdk.CfnOutput(this, 'DashboardName', { value: dashboard.dashboardName });
  }
}
