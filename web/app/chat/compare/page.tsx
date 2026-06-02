/**
 * /chat/compare → /chat redirect.
 *
 * 3-stage 비교 페이지는 사용자 신고 (각 stage 답변 박스가 *agent/agentic 전환 시 새 결과로 출력*)에 따라
 * 단일 답변 thread 패턴으로 통일. gcc 챗봇 패턴 차용 (3 stage 비교 narrative 없음).
 *
 * /chat 페이지: mode=agentic 단일 stream + phase ordered list + 단일 답변 박스.
 */
import { redirect } from 'next/navigation';

export default function CompareRedirect(): never {
  redirect('/chat');
}
