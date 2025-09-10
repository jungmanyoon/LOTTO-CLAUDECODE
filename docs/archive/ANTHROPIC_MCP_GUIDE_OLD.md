# Render.com MCP Server 통합 가이드

## 🤖 Render MCP Server란?

**Render MCP Server**는 AI 애플리케이션(Claude Code, Cursor 등)을 통해 자연어로 Render 인프라를 관리할 수 있게 해주는 호스팅 서비스입니다.

### 주요 특징:
- **자연어 인프라 관리**: AI를 통한 서비스 관리
- **Claude Code 통합**: Claude Code에서 직접 Render 서비스 제어
- **자동화 지원**: AI 명령으로 배포 및 관리

## 💰 Render MCP Server 비용

### 무료로 제공되는 기능 ✅
- **MCP Server 자체는 무료**
- **Render 계정만 있으면 사용 가능**
- **API 키 생성 무료**
- **Claude Code와 통합 무료**

### 실제 비용이 발생하는 부분
- **생성되는 서비스의 인스턴스 비용만 청구**
- **무료 인스턴스는 MCP로 생성 불가**
- **최소 Starter 플랜($7/월)부터 생성 가능**

## 🔗 로또 시스템과 Render MCP Server 활용

### 1. Render MCP Server 설정 (Claude Code)
```json
// .claude/mcp_settings.json
{
  "mcp": {
    "servers": {
      "render": {
        "command": "npx",
        "args": ["@render-oss/mcp-server"],
        "env": {
          "RENDER_API_KEY": "your-render-api-key-here"
        }
      }
    }
  }
}
```

### 2. Claude Code에서 자연어로 인프라 관리
```
사용 예시:
"Render에 lotto-prediction 웹 서비스를 Python 3.11로 생성해줘"
"lotto-ml-worker 서비스의 환경변수를 업데이트해줘"
"지난 24시간의 서비스 메트릭을 보여줘"
"데이터베이스 상태를 확인해줘"
```

### 3. API 엔드포인트로 노출
```python
# api_server.py
from flask import Flask, request, jsonify
from mcp_server import LottoMCPServer

app = Flask(__name__)
mcp = LottoMCPServer()

@app.route('/mcp/tools', methods=['GET'])
def list_tools():
    """사용 가능한 MCP 도구 목록"""
    return jsonify({
        "tools": [
            "collect_lottery_data",
            "predict_numbers",
            "backtest"
        ]
    })

@app.route('/mcp/execute', methods=['POST'])
def execute_tool():
    """MCP 도구 실행"""
    data = request.json
    tool_name = data.get('tool')
    params = data.get('params', {})
    
    result = mcp.execute(tool_name, **params)
    return jsonify(result)

@app.route('/mcp/context', methods=['GET', 'POST'])
def manage_context():
    """컨텍스트 관리"""
    if request.method == 'GET':
        return jsonify(mcp.get_context())
    else:
        mcp.update_context(request.json)
        return jsonify({"status": "updated"})
```

## 🆓 무료 MCP 구현 전략

### 옵션 1: 로컬 MCP 서버
```bash
# 로컬에서 MCP 서버 실행
python mcp_server.py

# ngrok으로 외부 노출 (무료)
ngrok http 3000
```

### 옵션 2: Cloudflare Workers (무료)
```javascript
// mcp-worker.js
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    
    if (url.pathname === '/mcp/predict') {
      // 예측 로직
      return Response.json({
        numbers: generatePrediction(),
        timestamp: new Date().toISOString()
      });
    }
    
    return Response.json({
      error: "Unknown endpoint"
    }, { status: 404 });
  }
};
```

### 옵션 3: Vercel Serverless (무료)
```javascript
// api/mcp/[tool].js
export default function handler(req, res) {
  const { tool } = req.query;
  const { params } = req.body;
  
  switch(tool) {
    case 'predict':
      res.json(predictNumbers(params));
      break;
    case 'collect':
      res.json(collectData(params));
      break;
    default:
      res.status(404).json({ error: 'Tool not found' });
  }
}
```

## 📊 비용 비교

| 방식 | 초기 비용 | 월 비용 | 제한사항 |
|------|-----------|---------|----------|
| 로컬 MCP | $0 | $0 | 인터넷 연결 필요 |
| Cloudflare Workers | $0 | $0 | 100K 요청/일 |
| Vercel Serverless | $0 | $0 | 100GB 대역폭 |
| Claude API 직접 | $0 | 사용량 기반 | API 키 필요 |
| Render + MCP | $0 | $7+ | 슬립 모드 |

## 🚀 추천 구현 방식

### 개발/테스트 단계
```yaml
구성:
  - 로컬 MCP 서버 (무료)
  - ngrok 터널링 (무료)
  - Claude Code 로컬 테스트
  
장점:
  - 완전 무료
  - 빠른 개발 사이클
  - 디버깅 용이
```

### 프로덕션 단계
```yaml
구성:
  - Vercel Serverless Functions (무료)
  - Supabase Database (무료)
  - GitHub Actions 스케줄러 (무료)
  
장점:
  - 완전 무료 운영
  - 확장 가능
  - 안정적
```

## 💡 실제 구현 예제

### 1. 최소 MCP 서버 (30줄)
```python
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/mcp/status")
def status():
    return {"status": "active", "version": "1.0"}

@app.post("/mcp/predict")
def predict():
    # 간단한 예측 로직
    import random
    numbers = sorted(random.sample(range(1, 46), 6))
    return {"numbers": numbers}

@app.get("/mcp/history")
def history():
    # 최근 당첨번호
    return {
        "latest": [7, 11, 16, 21, 27, 33],
        "round": 1186
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000)
```

### 2. Claude Code 통합 설정
```json
{
  "mcp_servers": {
    "lotto": {
      "endpoint": "http://localhost:3000/mcp",
      "auth": "none",
      "tools": ["predict", "history", "status"]
    }
  }
}
```

## 📝 결론

### MCP 통합의 장점:
✅ AI와 로또 시스템의 자연스러운 통합
✅ Claude를 통한 지능적인 분석
✅ 자동화된 워크플로우

### 무료 운영 가능 여부:
✅ **MCP 프로토콜 자체는 무료**
✅ **자체 서버 구현시 무료**
❌ **Claude API 사용시 유료**

### 권장사항:
1. **개발 단계**: 로컬 MCP 서버로 시작
2. **테스트 단계**: Vercel/Cloudflare 무료 티어 활용
3. **운영 단계**: 비용 대비 효과 고려하여 유료 전환

## 🔗 참고 자료

- [MCP 공식 문서](https://modelcontextprotocol.io)
- [Claude API 가격](https://www.anthropic.com/pricing)
- [Vercel 무료 티어](https://vercel.com/pricing)
- [Cloudflare Workers 무료 티어](https://workers.cloudflare.com)