# Lotto Prediction System - Custom Skills

이 디렉토리는 로또 예측 시스템 개발을 위한 Claude Code 전문 Skills를 포함합니다.

## 📚 Available Skills

### 1. **Lotto Filter Expert** (`lotto-filter-expert`)
- **전문 분야**: 16개 필터 시스템, 적응형 확률 필터링, 임계값 최적화
- **사용 시기**: 필터 시스템 수정, 임계값 조정, ML-필터 통합 문제
- **핵심 파일**: `adaptive_probability_filter.py`, `filter_manager.py`, `threshold_manager.py`

### 2. **Lotto ML Trainer** (`lotto-ml-trainer`)
- **전문 분야**: ML 모델 학습, 최적화, 캐싱, 앙상블 예측
- **사용 시기**: 모델 재학습, 캐시 문제, 성능 점수 계산, TensorFlow 설정
- **핵심 모델**: LSTM, XGBoost, Monte Carlo, Bayesian, Fractal

### 3. **Lotto Database Manager** (`lotto-db-manager`)
- **전문 분야**: 데이터베이스 작업, 스키마 관리, 인덱싱, 쿼리 최적화
- **사용 시기**: DB 스키마 수정, 쿼리 성능 문제, 데이터 무결성, 마이그레이션
- **핵심 기능**: 12개 전략적 인덱스, 보너스 번호 처리, 자동 최적화

### 4. **Lotto Backtester** (`lotto-backtester`)
- **전문 분야**: 백테스팅, 성능 검증, 등수 계산, Optuna 자동 최적화
- **사용 시기**: 백테스팅 설정, 성능 분석, 임계값 튜닝, 누적 학습 관리
- **핵심 시스템**: OptimizedBacktestingFramework, ThresholdOptimizer, SmartAutoLearning

### 5. **Lotto Troubleshooter** (`lotto-troubleshooter`)
- **전문 분야**: 문제 진단 및 해결, 시스템 건강 체크, 자동 복구, 메모리 관리
- **사용 시기**: 시스템 에러, 성능 저하, 메모리 문제, 일반적인 문제 해결
- **핵심 도구**: SystemHealthChecker, AutoRepairSystem, MemoryMonitor

## 🚀 How Skills Work

### Automatic Activation
Claude Code는 작업 컨텍스트를 분석하여 자동으로 적절한 Skill을 활성화합니다:

```
User: "필터 시스템의 임계값을 조정하고 싶어"
→ Claude activates: Lotto Filter Expert Skill
→ Provides expert guidance on threshold management
```

### Manual Invocation
특정 Skill을 명시적으로 호출할 수도 있습니다:

```bash
# In Claude Code
/skill lotto-filter-expert
/skill lotto-ml-trainer
/skill lotto-db-manager
/skill lotto-backtester
/skill lotto-troubleshooter
```

## 📖 Skill Structure

각 Skill은 다음 구조를 따릅니다:

```
skill-name/
└── Skill.md           # Skill definition with YAML frontmatter
```

**Skill.md Format:**
```markdown
---
name: Skill Name
description: Brief description (max 200 chars)
---

# Skill Name

[Detailed instructions, best practices, examples, etc.]
```

## 🔧 Installation & Setup

이 Skills는 프로젝트에 이미 설치되어 있으며, Claude Code가 자동으로 인식합니다.

### Directory Structure
```
D:\VisualStudio\04.로또_신버전\250727_CLAUDE CODE_R0\
└── .claude/
    └── skills/
        ├── README.md (this file)
        ├── lotto-filter-expert/
        │   └── Skill.md
        ├── lotto-ml-trainer/
        │   └── Skill.md
        ├── lotto-db-manager/
        │   └── Skill.md
        ├── lotto-backtester/
        │   └── Skill.md
        └── lotto-troubleshooter/
            └── Skill.md
```

## 🎯 Usage Examples

### Example 1: Filter System Modification
```
User: "AdaptiveProbabilityFilter의 임계값을 1.5%로 변경하고 싶어"
Claude: [Activates Lotto Filter Expert]
        - ThresholdManager 사용법 안내
        - adaptive_filter_config.yaml 수정 방법
        - 변경 후 검증 절차
        - ML-필터 통합 영향 분석
```

### Example 2: ML Model Training Issue
```
User: "LSTM 모델 학습 중 AttributeError가 발생해"
Claude: [Activates Lotto ML Trainer]
        - StandardScaler AttributeError 진단
        - 캐시 손상 확인
        - clear_model_cache.py 실행 안내
        - TensorFlow 설정 확인
```

### Example 3: Database Performance Issue
```
User: "DELETE 쿼리가 너무 느려"
Claude: [Activates Lotto Database Manager]
        - 12개 전략적 인덱스 확인
        - 인덱스 자동 생성 확인
        - 쿼리 실행 계획 분석
        - 성능 벤치마크 제공
```

### Example 4: Backtesting Validation
```
User: "백테스팅 결과의 평균 매칭이 3.5인데 이게 정상이야?"
Claude: [Activates Lotto Backtester]
        - 평균 매칭 >3 경고 (데이터 오염 가능성)
        - 데이터 분할 로직 확인 안내
        - 정상 범위 (0.6-2.0) 설명
        - 검증 절차 제공
```

### Example 5: General Troubleshooting
```
User: "프로그램이 메모리를 4GB 이상 사용해"
Claude: [Activates Lotto Troubleshooter]
        - MemoryMonitor로 사용량 확인
        - auto_cache_cleaner.py 실행 안내
        - config.yaml 배치 사이즈 조정
        - 메모리 최적화 전략 제공
```

## 💡 Best Practices

### For Developers
1. **컨텍스트 명확히 제공**: "필터 성능이 안 좋아" → "AdaptiveProbabilityFilter의 inclusion rate이 8%인데 목표 15%를 달성하고 싶어"
2. **관련 파일 언급**: Skill이 더 정확한 컨텍스트를 파악할 수 있습니다
3. **에러 메시지 포함**: 전체 에러 메시지를 포함하면 더 빠른 진단 가능
4. **변경 사항 검증**: Skill의 안내에 따라 변경 후 반드시 검증

### For Claude Code
1. **Skill 자동 활성화**: Description을 기반으로 자동 선택
2. **여러 Skill 조합**: 복잡한 문제는 여러 Skill 활용 가능
3. **프로젝트 컨텍스트 유지**: CLAUDE.md와 함께 사용
4. **전문성 활용**: 각 Skill의 전문 지식을 최대한 활용

## 📊 Skill Effectiveness

각 Skill은 다음 정보를 제공합니다:

- ✅ **Core Responsibilities**: 핵심 책임과 전문 영역
- ✅ **Common Issues & Solutions**: 일반적인 문제와 해결책
- ✅ **Key Files**: 관련 핵심 파일 목록
- ✅ **Critical Rules**: 반드시 따라야 할 규칙
- ✅ **Example Commands**: 실제 사용 예제
- ✅ **Performance Metrics**: 성능 지표 및 목표

## 🔄 Continuous Improvement

Skills는 프로젝트와 함께 진화합니다:

1. **새로운 기능 추가**: Skill.md 업데이트
2. **문제 해결 사례 추가**: Common Issues 섹션 확장
3. **Best Practices 개선**: 실제 경험 반영
4. **Example Commands 추가**: 유용한 명령어 문서화

## 📝 Notes

- **프로젝트 특화**: 이 Skills는 로또 예측 시스템에 특화되어 있습니다
- **CLAUDE.md 보완**: CLAUDE.md와 함께 사용하여 최대 효과 발휘
- **자동 업데이트**: 프로젝트 변경 시 Skill도 함께 업데이트 필요
- **팀 공유**: Git에 체크인되어 팀원 모두 사용 가능

## 🤝 Contributing

새로운 Skill 추가 또는 기존 Skill 개선:

1. 적절한 디렉토리 생성 또는 선택
2. Skill.md 작성 (YAML frontmatter 필수)
3. Description은 200자 이내로 명확하게
4. 실제 사용 예제와 Best Practices 포함
5. Git에 커밋하여 팀과 공유

## 📚 References

- [Claude Code Skills Documentation](https://docs.claude.com/en/docs/claude-code/skills)
- [Anthropic Skills Repository](https://github.com/anthropics/skills)
- [Creating Custom Skills Guide](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills)

---

**Last Updated**: 2025-10-18
**Skills Version**: 1.0.0
**Project**: Lotto Prediction System v250727_R0
