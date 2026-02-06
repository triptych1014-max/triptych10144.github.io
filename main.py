import os
import sys
import requests
import json
from datetime import datetime
from jira import JIRA
import google.generativeai as genai

# === 1. 환경 변수 로드 ===
JIRA_SERVER = os.environ.get("JIRA_SERVER")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
JIRA_TOKEN = os.environ.get("JIRA_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
KAKAOWORK_WEBHOOK_URL = os.environ.get("KAKAOWORK_WEBHOOK_URL")

# === 2. 검색할 키워드 설정 ===
TARGET_KEYWORDS = ["604", "624", "704"] 

def get_jira_issues_by_keyword():
    """Jira 이슈 수집 함수"""
    combined_data = ""
    found_any_issue = False

    try:
        # Jira 연결 인증
        jira = JIRA(server=JIRA_SERVER, basic_auth=(JIRA_EMAIL, JIRA_TOKEN))
        
        for keyword in TARGET_KEYWORDS:
            print(f"🔍 '{keyword}' 관련 이슈 검색 중...")
            
            # 검색 조건: 요약(summary) 또는 본문(text)에 키워드 포함 + 최근 30일 이내 업데이트
            jql_query = f'(summary ~ "{keyword}" OR text ~ "{keyword}") AND updated >= "-30d" ORDER BY updated DESC'
            issues = jira.search_issues(jql_query, maxResults=10)
            
            if not issues:
                combined_data += f"\n### [{keyword}] 관련 최근 이슈 없음\n"
                continue
                
            found_any_issue = True
            combined_data += f"\n### [{keyword}] 관련 이슈 ({len(issues)}건)\n"
            
            for issue in issues:
                summary = issue.fields.summary
                status = issue.fields.status.name
                assignee = issue.fields.assignee.displayName if issue.fields.assignee else "담당자 없음"
                updated_date = issue.fields.updated[:10]
                
                combined_data += f"- **[{issue.key}]** {summary} (상태: {status} | 담당: {assignee} | 수정일: {updated_date})\n"
        
        return combined_data if found_any_issue else None
        
    except Exception as e:
        print(f"❌ Jira 연결 또는 검색 오류: {e}")
        return None

def summarize_with_gemini(text_data):
    """Gemini API를 사용하여 요약 생성"""
    if not text_data:
        return None

    try:
        # ✅ 모델명 수정: 'gemini-1.5-flash'가 현재 가장 안정적인 무료 티어 모델입니다.
        model_name = "gemini-1.5-flash"
        print(f"🤖 선택된 AI 모델: {model_name}")

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(model_name)

        prompt = f"""
        당신은 IT 프로젝트 매니저입니다. 아래 Jira 이슈 데이터를 분석하여 주간 보고서를 작성하세요.
        
        [요청사항]
        1. [{', '.join(TARGET_KEYWORDS)}] 키워드별로 섹션을 나누어 정리하세요.
        2. 각 섹션마다 '현황 요약', '주요 이슈(ID포함)'를 포함하세요.
        3. 이슈가 없는 키워드는 "특이사항 없음"으로 명시하세요.
        4. 가독성 좋게 불렛포인트를 사용하여 작성하세요.

        [데이터]
        {text_data}
        """

        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        print(f"❌ Gemini API 요약 오류: {e}")
        return None

def send_kakaowork_message(summary_text):
    """카카오워크 블록키트 전송 함수"""
    if not KAKAOWORK_WEBHOOK_URL:
        print("❌ 에러: KAKAOWORK_WEBHOOK_URL이 설정되지 않았습니다.")
        return

    # 텍스트가 너무 길면 카카오워크에서 거절될 수 있으므로 제한 (약 3,000자 내외 안전)
    safe_summary = (summary_text[:2500] + '...') if len(summary_text) > 2500 else summary_text

    # 카카오워크 블록키트 페이로드
    payload = {
        "text": "Jira 주간 리포트 알림",
        "blocks": [
            {
                "type": "header",
                "text": "📅 Jira 주간 리포트",
                "style": "blue"
            },
            {
                "type": "section",
                "content": {
                    "type": "text",
                    "text": safe_summary,
                    "markdown": True
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "action",
                "elements": [
                    {
                        "type": "button",
                        "text": "Jira 서버 바로가기",
                        "style": "primary",
                        "action_type": "open_external_app",
                        "value": JIRA_SERVER
                    }
                ]
            }
        ]
    }

    try:
        headers = {"Content-Type": "application/json"}
        # json 파라미터를 사용하여 딕셔너리를 JSON 문자로 자동 변환
        response = requests.post(KAKAOWORK_WEBHOOK_URL, json=payload, headers=headers)
        
        if response.status_code == 200:
            print("✅ 카카오워크 메시지 전송 성공!")
        else:
            print(f"❌ 전송 실패 (코드: {response.status_code})")
            print(f"🔍 상세 에러: {response.text}")
    except Exception as e:
        print(f"❌ 카카오워크 요청 중 예외 발생: {e}")

# === 메인 실행 로직 ===
if __name__ == "__main__":
    print(f"🚀 스크립트 실행 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. Jira 데이터 수집
    raw_data = get_jira_issues_by_keyword()
    
    if raw_data:
        print("📝 데이터 수집 완료, AI 요약 진행 중...")
        # 2. Gemini 요약
        summary = summarize_with_gemini(raw_data)
        
        if summary:
            print("📩 카카오워크 전송 중...")
            # 3. 메시지 전송 (함수 이름 수정됨)
            send_kakaowork_message(summary)
        else:
            print("⚠️ 요약 결과가 비어있습니다.")
    else:
        print("⚠️ 수집된 데이터가 없습니다. 알림을 건너뜁니다.")
        # 데이터가 없을 때도 알림을 보내고 싶다면 아래 주석을 해제하세요.
        # send_kakaowork_message("이번 주 검색된 Jira 이슈가 없습니다.")
