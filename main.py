import os
import sys
from jira import JIRA
from openai import OpenAI
import requests
from datetime import datetime

# === 환경 변수 로드 ===
# 로컬 테스트 시에는 os.environ.get 대신 직접 값을 넣어서 테스트 가능하지만,
# GitHub Actions 배포를 위해 아래 방식을 유지하는 것이 좋습니다.
JIRA_SERVER = os.environ.get("JIRA_SERVER") # 예: https://your-company.atlassian.net
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")   # 예: name@company.com
JIRA_TOKEN = os.environ.get("JIRA_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

# 검색할 키워드 설정 (필요에 따라 수정)
TARGET_KEYWORD = "결제" 

def get_jira_issues():
    """Jira에서 특정 키워드와 기간으로 이슈를 수집합니다."""
    try:
        jira = JIRA(server=JIRA_SERVER, basic_auth=(JIRA_EMAIL, JIRA_TOKEN))
        # JQL: 키워드 포함 + 최근 7일 생성 + 생성일 역순 정렬
        jql_query = f'text ~ "{TARGET_KEYWORD}" AND created >= "-7d" ORDER BY created DESC'
        issues = jira.search_issues(jql_query, max_results=30)
        
        if not issues:
            print("검색된 이슈가 없습니다.")
            return None
            
        print(f"총 {len(issues)}개의 이슈를 발견했습니다.")
        
        # AI에게 던져줄 텍스트 데이터 가공
        issue_text = ""
        for issue in issues:
            summary = issue.fields.summary
            status = issue.fields.status.name
            assignee = issue.fields.assignee.displayName if issue.fields.assignee else "담당자 없음"
            # 설명이 너무 길면 200자로 자름
            description = (issue.fields.description[:200] + "...") if issue.fields.description else "설명 없음"
            
            issue_text += f"ID: {issue.key} | 상태: {status} | 담당: {assignee}\n제목: {summary}\n내용: {description}\n---\n"
            
        return issue_text
        
    except Exception as e:
        print(f"Jira 연결 오류: {e}")
        return None

def summarize_with_gpt(text_data):
    """OpenAI GPT-4를 사용하여 이슈 내용을 요약합니다."""
    if not text_data:
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)
    
    prompt = f"""
    아래는 최근 일주일간 '{TARGET_KEYWORD}'와 관련된 Jira 이슈 목록입니다.
    팀장님께 보고할 수 있도록 다음 형식으로 깔끔하게 요약해주세요:
    
    1. **현황 요약**: 전체적인 진행 상황 한 줄 요약
    2. **주요 이슈**: (진행 중이거나 완료된 중요 티켓 3~4개)
    3. **주의 필요**: (상태가 'Blocked'이거나 담당자가 없는 등 문제가 될만한 것)
    
    [데이터]
    {text_data}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4", # 또는 gpt-3.5-turbo (비용 절약 시)
            messages=[
                {"role": "system", "content": "당신은 유능한 IT 프로젝트 매니저입니다."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI API 오류: {e}")
        return None

def send_slack_alert(message):
    """요약된 내용을 슬랙으로 전송합니다."""
    if not message:
        return

    payload = {
        "text": f"📢 *주간 '{TARGET_KEYWORD}' 이슈 리포트* ({datetime.now().strftime('%Y-%m-%d')})",
        "attachments": [
            {
                "color": "#36a64f",
                "text": message
            }
        ]
    }
    
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload)
        response.raise_for_status()
        print("슬랙 전송 완료!")
    except Exception as e:
        print(f"슬랙 전송 오류: {e}")

# === 메인 실행 함수 ===
if __name__ == "__main__":
    # 1. Jira 데이터 수집
    raw_data = get_jira_issues()
    
    # 2. 데이터가 있을 경우에만 요약 및 전송
    if raw_data:
        summary = summarize_with_gpt(raw_data)
        if summary:
            send_slack_alert(summary)
    else:
        print("처리할 데이터가 없어 종료합니다.")