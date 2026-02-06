import os
import sys
from jira import JIRA
import google.generativeai as genai
import requests
from datetime import datetime

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
        jira = JIRA(server=JIRA_SERVER, basic_auth=(JIRA_EMAIL, JIRA_TOKEN))
        
        for keyword in TARGET_KEYWORDS:
            print(f"🔍 '{keyword}' 관련 이슈 검색 중...")
            
            # 검색 조건: 제목/내용 포함 OR 최근 30일 내 업데이트
            jql_query = f'(summary ~ "{keyword}" OR text ~ "{keyword}") AND updated >= "-30d" ORDER BY updated DESC'
            issues = jira.search_issues(jql_query, maxResults=10)
            
            if not issues:
                combined_data += f"\n=== [{keyword}] 관련 최근 이슈 없음 ===\n"
                continue
                
            found_any_issue = True
            combined_data += f"\n=== [{keyword}] 관련 이슈 ({len(issues)}건) ===\n"
            
            for issue in issues:
                summary = issue.fields.summary
                status = issue.fields.status.name
                assignee = issue.fields.assignee.displayName if issue.fields.assignee else "담당자 없음"
                desc_raw = issue.fields.description if issue.fields.description else "내용 없음"
                description = (desc_raw[:150] + "...") 
                updated_date = issue.fields.updated[:10]
                
                combined_data += f"- [{issue.key}] {summary} (상태: {status} | 담당: {assignee} | 수정일: {updated_date})\n"
        
        return combined_data if found_any_issue else None
        
    except Exception as e:
        print(f"❌ Jira 연결 또는 검색 오류: {e}")
        return None

def summarize_with_gemini(text_data):
    """Gemini 2.0 Flash 모델을 사용하여 요약합니다."""
    if not text_data:
        return None

    try:
        # ✅ 수정됨: 무료 티어에서 가장 확실한 Flash 모델 고정 사용
        # 로그에 있던 'models/gemini-2.0-flash'를 사용합니다.
        model_name = "models/gemini-2.5-flash-lite"
        
        print(f"🤖 선택된 AI 모델: {model_name}")

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(model_name)

        prompt = f"""
        당신은 IT 프로젝트 매니저입니다. 아래 Jira 이슈 데이터를 분석하여 주간 보고서를 작성하세요.
        
        [요청사항]
        1. [{', '.join(TARGET_KEYWORDS)}] 키워드별로 섹션을 나누세요.
        2. 각 섹션마다 '현황 요약', '주요 이슈(ID포함)'를 정리하세요.
        3. 이슈가 없는 키워드는 "특이사항 없음"으로 명시하세요.
        4. 가독성 좋은 마크다운 형식으로 작성하세요.

        [데이터]
        {text_data}
        """

        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        print(f"❌ Gemini API 요약 오류: {e}")
        return None

def send_kakaowork_message(summary_text):
    webhook_url = os.getenv("KAKAOWORK_WEBHOOK_URL")
    
    # 1. 안전한 텍스트 처리 (너무 길면 자르기)
    safe_summary = (summary_text[:300] + '...') if len(summary_text) > 300 else summary_text

    # 2. 규격에 맞춘 블록키트 구성
    payload = {
        "text": "Jira 주간 리포트 알림", # 필수: 알림 센터에 표시될 텍스트
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
                        "text": "Jira 열기",
                        "style": "primary",
                        "action_type": "open_external_app",
                        "value": os.getenv("JIRA_SERVER", "https://atlassian.net")
                    }
                ]
            }
        ]
    }

    headers = {"Content-Type": "application/json"}
    response = requests.post(webhook_url, json=payload) # json=으로 바로 전송 (추천)
    
    if response.status_code == 200:
        print("✅ 카카오워크 메시지 전송 성공!")
    else:
        # 400 에러 발생 시 카카오워크가 주는 구체적인 답변을 출력합니다.
        print(f"❌ 전송 실패 (상태 코드: {response.status_code})")
        print(f"🔍 상세 에러 내용: {response.text}")

# === 메인 실행 ===
if __name__ == "__main__":
    print("🚀 자동화 스크립트 시작 (Model: Gemini 2.0 Flash)")
    
    raw_data = get_jira_issues_by_keyword()
    
    if raw_data:
        print("📝 데이터 수집 완료, AI 요약 시작...")
        summary = summarize_with_gemini(raw_data)
        
        if summary:
            print("📩 카카오워크 전송 중...")
            send_kakaowork_alert(summary)
    else:
        print("⚠️ 수집된 데이터가 없습니다.")
        send_kakaowork_alert("설정된 키워드로 검색된 최근 이슈가 없습니다.")



