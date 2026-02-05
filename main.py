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

def get_best_gemini_model():
    """사용 가능한 모델 목록을 조회하여 최적의 모델 이름을 반환합니다."""
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        
        # 사용 가능한 모델 리스트 가져오기
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        print(f"ℹ️ 사용 가능한 모델 목록: {available_models}")

        # 우선순위: 1.5-flash -> 1.5-pro -> 1.0-pro -> 아무거나
        for model in available_models:
            if "gemini-1.5-flash" in model:
                return model
        for model in available_models:
            if "gemini-1.5-pro" in model:
                return model
        for model in available_models:
            if "gemini-pro" in model:
                return model
        
        # 위 모델들이 없으면 목록의 첫 번째 모델 반환
        if available_models:
            return available_models[0]
        else:
            return None

    except Exception as e:
        print(f"⚠️ 모델 목록 조회 실패: {e}")
        return "models/gemini-pro" # 실패 시 기본값 시도

def summarize_with_gemini(text_data):
    """자동으로 찾은 모델을 사용하여 요약합니다."""
    if not text_data:
        return None

    try:
        # 1. 최적의 모델명 찾기
        model_name = get_best_gemini_model()
        print(f"🤖 선택된 AI 모델: {model_name}")

        if not model_name:
            print("❌ 사용 가능한 Gemini 모델을 찾을 수 없습니다.")
            return None

        # 2. 모델 설정 및 호출
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

def send_kakaowork_alert(message):
    """카카오워크 전송"""
    if not message:
        return

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
        print("✅ 카카오워크 전송 완료!")
    except Exception as e:
        print(f"❌ 카카오워크 전송 오류: {e}")

# === 메인 실행 ===
if __name__ == "__main__":
    print("🚀 자동화 스크립트 시작 (Auto-Detect Model)")
    
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
