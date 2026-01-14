import psycopg2
import requests
import time

def test_db():
    print("\n[1] DB 연결 테스트 중...")
    try:
        # 아까 설정한 docker-compose.yml 정보 그대로
        conn = psycopg2.connect(
            host="localhost",      # kkh60이 띄운 서버는 remote에게도 localhost
            port="5432",
            database="postgre",
            user="postgre",
            password="1234"
        )
        print("✅ PostgreSQL 연결 성공! (버전 정보:)")
        cur = conn.cursor()
        cur.execute("SELECT version();")
        print(f"   -> {cur.fetchone()[0]}")
        conn.close()
    except Exception as e:
        print(f"❌ DB 연결 실패: {e}")

def test_ai():
    print("\n[2] AI(Ollama) 연결 테스트 중...")
    try:
        # Llama3에게 간단한 인사 건네기
        start_time = time.time()
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3",
                "prompt": "Hello! Are you running on GPU?",
                "stream": False
            }
        )
        end_time = time.time()
        
        if response.status_code == 200:
            result = response.json()['response']
            print(f"✅ AI 응답 성공! (소요시간: {end_time - start_time:.2f}초)")
            print(f"   -> 답변: {result.strip()[:50]}...") # 답변 앞부분만 출력
        else:
            print(f"❌ AI 응답 오류: {response.status_code}")
            
    except Exception as e:
        print(f"❌ AI 연결 실패: {e}")

if __name__ == "__main__":
    print("=== 🚀 인프라 연결 진단 시작 ===")
    test_db()
    test_ai()
    print("\n=== 진단 종료 ===")