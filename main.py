import os
import sys
from jira import JIRA
from openai import OpenAI
import requests
from datetime import datetime

# === 환경 변수 로드 ===
JIRA_SERVER = os.environ.get("JIRA_SERVER")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
JIRA_TOKEN = os.environ.get("JIRA_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
KAKAOWORK_WEBHOOK_URL = os.environ.get("KAKAOWORK_WEBHOOK_URL")

# ✅ 수정됨: 분석하고 싶은 키워드 3가지를 리스트로 설정
# 필요한 키워드로 아래 내용을 변경하세요.
TARGET_KEYWORDS = ["604", "624", "704"] 

def get_jira_issues_by_keyword():
    """설정된 키워드 리스트를 순회하며 이슈를 수집합니다."""
    
    combined_data = ""
    found_any_issue = False

    try:
        jira = JIRA(server=JIRA_SERVER, basic_auth=(JIRA_EMAIL, JIRA_TOKEN))
        
        # 각 키워드별로 반복 실행
        for keyword in TARGET_KEYWORDS:
            print(f"🔍 '{keyword}' 검색 중...")
            
            # JQL: 키워드 포함 + 최근 7일 생성 + 생성일 역순
            jql_query = f'text ~ "{keyword}" AND created >= "-7d" ORDER BY created DESC'
            issues = jira.search_issues(jql_query, max_results=15) # 키워드가 여러개니 개수 제한을 조금 줄임
            
            if not issues:
                combined_data += f"\n=== [{keyword}] 관련 이슈 없음 ===\n"
                continue
                
            found_any_issue = True
            combined_data += f"\n=== [{keyword}] 관련 이슈 ({len(issues)}건) ===\n"
            
            for issue in issues:
                summary = issue.fields.summary
                status = issue.fields.status.name
                assignee = issue.fields.assignee.displayName if issue.fields.assignee else "담당자 없음"
                description = (issue.fields.description[:100] + "...") if issue.fields.description else "내용 없음"
                
                combined_data += f"- [{status}] {summary} (담당: {assignee})\n  내용: {description}\n"
        
        return combined_data if found_any_issue else None
        
    except Exception as e:
        print(f"Jira 연결 오류: {e}")
        return None

def summarize_with_gpt(text_data):
    """OpenAI GPT-4를 사용하여 이슈 내용을 키워드별로 요약합니다."""
    if not text_data:
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)
    
    # ✅ 수정됨: 3가지 키워드를 구분해서 요약하라는 프롬프트
    prompt = f"""
    아래는 최근 일주일간 진행된 Jira 이슈 리스트입니다.
    데이터는 [{', '.join(TARGET_KEYWORDS)}] 키워드별로 구분되어 있습니다.

    IT 프로젝트 매니저 관점에서 **키워드별로 섹션을 나누어** 요약 보고서를 작성해주세요.
    
    [작성 양식]
    ## 1. {TARGET_KEYWORDS[0]}
    - **현황**: (진행 상황 한 줄 요약)
    - **핵심 이슈**: (주요 티켓 내용)

    ## 2. {TARGET_KEYWORDS[1]}
    ... (위와 동일)

    ## 3. {TARGET_KEYWORDS[2]}
    ... (위와 동일)
    
    [전체 종합 제언]
    - (전체 데이터를 봤을 때 주의할 점이나 발견된 패턴 1가지)

    [데이터]
    {text_data}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4", 
            messages=[
                {"role": "system", "content": "당신은 핵심을 잘 파악하는 수석 PM입니다. 마크다운 형식을 사용하여 가독성 있게 작성하세요."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI API 오류: {e}")
        return None

def send_kakaowork_alert(message):
    """요약된 내용을 카카오워크로 전송합니다."""
    if not message:
        return

    # 제목에 키워드들을 나열
    title_text = ", ".join(TARGET_KEYWORDS)

    payload = {
        "text": f"📢 주간 이슈 리포트 ({title_text})",
        "blocks": [
            {
                "type": "header",
                "text": "📢 주간 통합 이슈 리포트",
                "style": "blue"
            },
            {
                "type": "text",
                "text": f"**대상 키워드:** {title_text}",
                "markdown": True
            },
            {
                "type": "divider"
            },
            {
                "type": "text",
                "text": message,
                "markdown": True
            },
            {
                "type": "context",
                "content": {
                    "type": "text",
                    "text": f"발송 시간: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                },
                "image": {
                    "type": "image_link",
                    "url": "https://cdn-icons-png.flaticon.com/512/25/25231.png"
                }
            }
        ]
    }
    
    try:
        response = requests.post(KAKAOWORK_WEBHOOK_URL, json=payload)
        response.raise_for_status()
        print("카카오워크 전송 완료!")
    except Exception as e:
        print(f"카카오워크 전송 오류: {e}")

# === 메인 실행 함수 ===
if __name__ == "__main__":
    print("🚀 자동화 스크립트 시작")
    
    # 1. Jira 데이터 수집 (3개 키워드 통합)
    raw_data = get_jira_issues_by_keyword()
    
    # 2. 데이터가 있을 경우에만 요약 및 전송
    if raw_data:
        print("📝 데이터 수집 완료, AI 요약 시작...")
        summary = summarize_with_gpt(raw_data)
        
        if summary:
            print("📩 카카오워크 전송 중...")
            send_kakaowork_alert(summary)
    else:
        print("❌ 처리할 데이터가 없거나 오류가 발생하여 종료합니다.")
