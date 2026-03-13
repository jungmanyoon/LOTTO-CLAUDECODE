# ML 역할 재정의 설계 문서

## 현재 상태 분석

### 문제
- ML 모델(LSTM, Ensemble, MC, Bayesian)의 avg_matches ~= 0.8 (랜덤과 동일)
- 로또는 독립 사건: 과거 데이터로 미래 예측은 정보 이론상 불가능
- LSTM의 noisy_probs = probs + np.random.normal(0, 0.1) -> 사실상 랜덤 선택

### 현재 ML 역할: "미래 번호 예측" (이론적으로 불가능)

## 새로운 ML 역할 제안

### 역할 A: 필터 임계값 최적화 (현재 Optuna가 담당)
- **이미 구현됨**: ThresholdOptimizer + Optuna
- **개선점**: Optuna의 실제 성능 피드백 복원 (Phase 1-2에서 수정)
- **추가 작업 없음**: 기존 시스템 활용

### 역할 B: 풀 내 다양성 극대화 (Maximum Diversity Selection)
- **목표**: 300K 풀에서 N세트 선택 시 서로 최대한 다른 조합 선택
- **방법**: 조합 간 해밍 거리(Hamming Distance) 최대화
- **구현 위치**: `src/utils/diversity_selector.py` (신규)
- **통합 위치**: main.py의 generate_final_predictions_enhanced() 풀 보충 단계

### 역할 C: Covering Design (Wheeling System과 연계)
- **이미 구현됨**: WheelingSystem의 greedy_covering 알고리즘
- **Phase 2-3에서 통합**: main.py에 WheelingSystem 연동

## 구현 계획

### 역할 B 구현: diversity_selector.py

```python
class DiversitySelector:
    """풀 내 최대 다양성 조합 선택"""

    def select_diverse(
        self,
        pool: List[str],          # 필터링된 조합 풀
        n_select: int = 5,         # 선택할 조합 수
        method: str = 'greedy'     # greedy | random_restart
    ) -> List[str]:
        """풀에서 서로 가장 다른 n_select개 조합 선택

        알고리즘 (Greedy Farthest-Point):
        1. 풀에서 랜덤 시작점 선택
        2. 기존 선택에서 가장 먼 조합을 다음으로 추가
        3. n_select개가 될 때까지 반복
        """
```

### 통합 계획
1. generate_final_predictions_enhanced()의 풀 보충 단계에서:
   - 기존: random.sample(available_combos, needed)
   - 변경: DiversitySelector.select_diverse(available_combos, needed)
2. ML 예측이 필터 통과한 경우에도 다양성 검사:
   - 이미 선택된 예측과 너무 유사하면 대체 조합 선택

## 정직한 사용자 커뮤니케이션

### 대시보드에 표시할 내용
- "ML 모델은 미래 번호를 예측하지 않습니다"
- "필터 시스템이 비합리적 조합을 제거합니다"
- "Wheeling System이 선택 다양성을 극대화합니다"
- "실제 확률 개선: 비용 효율 27배 (확률 자체는 불변)"
