"""StatisticalWeightCalculator 단위 테스트"""
import pytest
from unittest.mock import MagicMock, patch


def _make_mock_db(num_rounds=10):
    """테스트용 DB mock 생성"""
    db = MagicMock()
    # (round, (n1,n2,n3,n4,n5,n6,bonus)) 형태
    data = []
    for i in range(1, num_rounds + 1):
        nums = tuple(sorted([(i % 45) + 1,
                              (i * 2 % 45) + 1,
                              (i * 3 % 45) + 1,
                              (i * 4 % 45) + 1,
                              (i * 5 % 45) + 1,
                              (i * 6 % 45) + 1])) + ((i % 45) + 1,)
        data.append((i, nums))
    db.get_numbers_with_bonus.return_value = data
    return db


@pytest.fixture(autouse=True)
def reset_singleton():
    """각 테스트 전후 싱글톤 초기화"""
    from src.utils.statistical_weight_calculator import StatisticalWeightCalculator
    StatisticalWeightCalculator.reset_instance()
    yield
    StatisticalWeightCalculator.reset_instance()


class TestStatisticalWeightCalculatorInit:
    @pytest.mark.unit
    def test_singleton_returns_same_instance(self):
        from src.utils.statistical_weight_calculator import StatisticalWeightCalculator
        db = _make_mock_db()
        inst1 = StatisticalWeightCalculator.get_instance(db)
        inst2 = StatisticalWeightCalculator.get_instance()
        assert inst1 is inst2

    @pytest.mark.unit
    def test_first_call_without_db_raises(self):
        from src.utils.statistical_weight_calculator import StatisticalWeightCalculator
        with pytest.raises(RuntimeError):
            StatisticalWeightCalculator.get_instance()

    @pytest.mark.unit
    def test_loads_db_data(self):
        from src.utils.statistical_weight_calculator import StatisticalWeightCalculator
        db = _make_mock_db(num_rounds=50)
        calc = StatisticalWeightCalculator.get_instance(db)
        assert calc._total_draws == 50
        assert calc._ready is True

    @pytest.mark.unit
    def test_fallback_on_db_error(self):
        from src.utils.statistical_weight_calculator import StatisticalWeightCalculator
        db = MagicMock()
        db.get_numbers_with_bonus.side_effect = Exception("DB 오류")
        calc = StatisticalWeightCalculator.get_instance(db)
        # 폴백값으로 초기화되어도 ready
        assert calc._ready is True


class TestCalculateComboWeight:
    @pytest.fixture
    def calc(self):
        from src.utils.statistical_weight_calculator import StatisticalWeightCalculator
        db = _make_mock_db(num_rounds=100)
        return StatisticalWeightCalculator.get_instance(db)

    @pytest.mark.unit
    def test_returns_float_in_range(self, calc):
        result = calc.calculate_combo_weight([1, 7, 14, 27, 34, 40])
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    @pytest.mark.unit
    def test_empty_input_returns_neutral(self, calc):
        result = calc.calculate_combo_weight([])
        assert result == 0.5

    @pytest.mark.unit
    def test_high_freq_numbers_score_higher(self, calc):
        """고빈도 번호 조합이 저빈도 번호 조합보다 높아야 함"""
        from src.utils.statistical_weight_calculator import _STATIC_FREQ
        # 빈도 상위 6개
        top6 = sorted(_STATIC_FREQ.items(), key=lambda x: x[1], reverse=True)[:6]
        top_nums = sorted([n for n, _ in top6])
        # 빈도 하위 6개
        bot6 = sorted(_STATIC_FREQ.items(), key=lambda x: x[1])[:6]
        bot_nums = sorted([n for n, _ in bot6])

        score_top = calc.calculate_combo_weight(top_nums)
        score_bot = calc.calculate_combo_weight(bot_nums)
        assert score_top > score_bot

    @pytest.mark.unit
    def test_weight_breakdown_sums_correctly(self, calc):
        """각 요인 가중치 합산이 total과 일치"""
        numbers = [3, 11, 21, 27, 33, 40]
        bd = calc.get_weight_breakdown(numbers)
        expected = (
            calc.BETA_FREQ   * bd['freq']    +
            calc.BETA_DIGIT  * bd['digit']   +
            calc.BETA_ABS    * bd['absence'] +
            calc.BETA_PAIR   * bd['pair']    +
            calc.BETA_SUM    * bd['sum']
        )
        assert abs(bd['total'] - expected) < 1e-9

    @pytest.mark.unit
    def test_high_freq_pair_increases_score(self, calc):
        """고빈도 쌍 (11,21) 포함 시 점수 증가"""
        with_pair    = calc.calculate_combo_weight([11, 21, 5, 15, 30, 40])
        without_pair = calc.calculate_combo_weight([10, 20, 5, 15, 30, 40])
        assert with_pair >= without_pair


class TestIndividualWeights:
    @pytest.fixture
    def calc(self):
        from src.utils.statistical_weight_calculator import StatisticalWeightCalculator
        db = _make_mock_db(num_rounds=100)
        return StatisticalWeightCalculator.get_instance(db)

    @pytest.mark.unit
    def test_digit_weight_favors_34(self, calc):
        """끝자리 4(가중치 1.142)와 끝자리 9(가중치 0.846) 비교"""
        # 끝자리 4: 4, 14, 24, 34, 44
        # 끝자리 9: 9, 19, 29, 39
        score_4 = calc._digit_weight_normalized([4, 14, 24, 34, 44, 1])
        score_9 = calc._digit_weight_normalized([9, 19, 29, 39, 3, 13])
        assert score_4 > score_9

    @pytest.mark.unit
    def test_absence_weight_long_absent_higher(self, calc):
        """38회 미출현 번호가 0회 미출현보다 높은 점수"""
        absence_38 = {n: 38 for n in range(1, 46)}
        absence_0  = {n: 0  for n in range(1, 46)}
        score_38 = calc._absence_weight_normalized([1, 2, 3, 4, 5, 6], absence_38)
        score_0  = calc._absence_weight_normalized([1, 2, 3, 4, 5, 6], absence_0)
        assert score_38 > score_0

    @pytest.mark.unit
    def test_sum_weight_range(self, calc):
        """합계 160-180 구간이 80-120 구간보다 높음"""
        # 합계 ~165
        score_high = calc._sum_weight_normalized([25, 27, 29, 31, 33, 20])
        # 합계 ~50
        score_low  = calc._sum_weight_normalized([1, 2, 3, 14, 15, 16])
        assert score_high > score_low

    @pytest.mark.unit
    def test_normalized_range(self, calc):
        """모든 정규화 함수가 [0,1] 범위 반환"""
        nums = [1, 10, 20, 30, 40, 45]
        assert 0.0 <= calc._freq_weight_normalized(nums)    <= 1.0
        assert 0.0 <= calc._digit_weight_normalized(nums)   <= 1.0
        assert 0.0 <= calc._absence_weight_normalized(nums) <= 1.0
        assert 0.0 <= calc._pair_weight_normalized(nums)    <= 1.0
        assert 0.0 <= calc._sum_weight_normalized(nums)     <= 1.0


class TestAbsenceScoreFunction:
    @pytest.mark.unit
    def test_absence_score_values(self):
        from src.utils.statistical_weight_calculator import _absence_score_for_number
        assert _absence_score_for_number(0)  == 0.0
        assert _absence_score_for_number(10) == 0.0
        assert _absence_score_for_number(21) == pytest.approx(-0.03)
        assert _absence_score_for_number(38) == pytest.approx(0.07)
        assert _absence_score_for_number(50) == pytest.approx(0.07)

    @pytest.mark.unit
    def test_absence_score_monotone_in_range(self):
        """10~21 구간은 단조 감소"""
        from src.utils.statistical_weight_calculator import _absence_score_for_number
        scores = [_absence_score_for_number(n) for n in range(10, 22)]
        assert all(scores[i] >= scores[i+1] for i in range(len(scores)-1))


class TestHelperMethods:
    @pytest.fixture
    def calc(self):
        from src.utils.statistical_weight_calculator import StatisticalWeightCalculator
        db = _make_mock_db(num_rounds=100)
        return StatisticalWeightCalculator.get_instance(db)

    @pytest.mark.unit
    def test_get_hot_numbers_count(self, calc):
        hot = calc.get_hot_numbers(top_n=10)
        assert len(hot) == 10
        assert all(1 <= n <= 45 for n in hot)

    @pytest.mark.unit
    def test_get_cold_numbers_count(self, calc):
        cold = calc.get_cold_numbers(top_n=5)
        assert len(cold) == 5

    @pytest.mark.unit
    def test_get_long_absent_returns_sorted(self, calc):
        # 임의로 미출현 데이터 설정
        calc._current_absence = {n: n for n in range(1, 46)}
        result = calc.get_long_absent_numbers(threshold=20)
        assert all(cnt >= 20 for _, cnt in result)
        # 내림차순 정렬 확인
        counts = [cnt for _, cnt in result]
        assert counts == sorted(counts, reverse=True)

    @pytest.mark.unit
    def test_refresh_absence_data(self, calc):
        original = dict(calc._current_absence)
        # DB가 새 데이터를 반환하도록 업데이트
        calc.db_manager.get_numbers_with_bonus.return_value = [
            (1, (1, 2, 3, 4, 5, 6, 7))
        ]
        calc.refresh_absence_data()
        # 갱신 후 값이 변경됨
        assert calc._current_absence != original
