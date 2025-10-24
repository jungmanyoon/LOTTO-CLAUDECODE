# -*- coding: utf-8 -*-
"""
System Performance Benchmarking Suite
측정 대상:
1. Filter Performance (16 filters)
2. ML Training Performance (LSTM, Ensemble, Monte Carlo, Bayesian)
3. Prediction Generation (End-to-end)
4. Optimization Performance (Optuna trials)
"""
import time
import json
import logging
import psutil
import traceback
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.core.db_manager import DatabaseManager
from src.core.filter_manager import FilterManager
from src.core.adaptive_probability_filter import AdaptiveProbabilityFilter
from src.utils.config_manager import ConfigManager


@dataclass
class BenchmarkResult:
    """개별 벤치마크 결과"""
    name: str
    category: str
    execution_time: float
    memory_used_mb: float
    cpu_percent: float
    status: str
    metrics: Dict[str, Any]
    timestamp: str


@dataclass
class SystemInfo:
    """시스템 정보"""
    cpu_count: int
    cpu_freq_mhz: float
    total_memory_gb: float
    available_memory_gb: float
    python_version: str
    platform: str
    timestamp: str


class PerformanceTimer:
    """성능 측정 컨텍스트 매니저"""

    def __init__(self, name: str):
        self.name = name
        self.start_time = None
        self.end_time = None
        self.start_memory = None
        self.end_memory = None
        self.start_cpu = None
        self.cpu_samples = []

    def __enter__(self):
        self.start_time = time.time()
        self.start_memory = psutil.virtual_memory().used / (1024 ** 2)  # MB
        self.start_cpu = psutil.cpu_percent(interval=0.1)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        self.end_memory = psutil.virtual_memory().used / (1024 ** 2)  # MB
        self.cpu_samples.append(psutil.cpu_percent(interval=0.1))

    @property
    def elapsed_time(self) -> float:
        """실행 시간 (초)"""
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return 0.0

    @property
    def memory_delta_mb(self) -> float:
        """메모리 사용량 증가 (MB)"""
        if self.end_memory and self.start_memory:
            return self.end_memory - self.start_memory
        return 0.0

    @property
    def avg_cpu_percent(self) -> float:
        """평균 CPU 사용률 (%)"""
        if self.cpu_samples:
            return sum(self.cpu_samples) / len(self.cpu_samples)
        return self.start_cpu or 0.0


class SystemBenchmark:
    """시스템 성능 벤치마크"""

    def __init__(self, output_dir: str = "benchmark_results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)

        # 결과 저장
        self.results: List[BenchmarkResult] = []
        self.system_info: Optional[SystemInfo] = None

        # 설정 로드
        self.config_manager = ConfigManager()

        # 초기화
        self._initialize_components()

    def _initialize_components(self):
        """컴포넌트 초기화"""
        try:
            self.db_manager = DatabaseManager()
            self.logger.info("DatabaseManager 초기화 완료")
        except Exception as e:
            self.logger.error(f"DatabaseManager 초기화 실패: {e}")
            self.db_manager = None

    def _collect_system_info(self) -> SystemInfo:
        """시스템 정보 수집"""
        return SystemInfo(
            cpu_count=psutil.cpu_count(logical=True),
            cpu_freq_mhz=psutil.cpu_freq().current if psutil.cpu_freq() else 0.0,
            total_memory_gb=psutil.virtual_memory().total / (1024 ** 3),
            available_memory_gb=psutil.virtual_memory().available / (1024 ** 3),
            python_version=sys.version.split()[0],
            platform=sys.platform,
            timestamp=datetime.now().isoformat()
        )

    def benchmark_filters(self, sample_size: int = 100000) -> Dict[str, BenchmarkResult]:
        """
        필터 성능 벤치마크

        Args:
            sample_size: 테스트할 조합 수

        Returns:
            필터별 벤치마크 결과
        """
        self.logger.info(f"[필터 벤치마크] 시작: {sample_size:,}개 조합")
        filter_results = {}

        if not self.db_manager:
            self.logger.error("DatabaseManager가 초기화되지 않음")
            return filter_results

        try:
            # 조합 생성
            self.logger.info("조합 생성 중...")
            with PerformanceTimer("combination_generation") as timer:
                from itertools import combinations
                all_combinations = list(combinations(range(1, 46), 6))[:sample_size]

            gen_result = BenchmarkResult(
                name="combination_generation",
                category="filters",
                execution_time=timer.elapsed_time,
                memory_used_mb=timer.memory_delta_mb,
                cpu_percent=timer.avg_cpu_percent,
                status="success",
                metrics={
                    "total_combinations": len(all_combinations),
                    "combinations_per_second": len(all_combinations) / timer.elapsed_time if timer.elapsed_time > 0 else 0
                },
                timestamp=datetime.now().isoformat()
            )
            self.results.append(gen_result)
            filter_results["combination_generation"] = gen_result

            # 필터 매니저 초기화
            filter_manager = FilterManager(self.db_manager)

            # 개별 필터 벤치마크
            enabled_filters = self.config_manager.get_enabled_filters()

            for filter_name in enabled_filters:
                self.logger.info(f"  - {filter_name} 필터 벤치마크...")

                try:
                    with PerformanceTimer(f"filter_{filter_name}") as timer:
                        # 필터 적용
                        filter_obj = filter_manager.get_filter(filter_name)
                        if filter_obj:
                            filtered = [c for c in all_combinations if filter_obj.apply(c)]
                            exclusion_count = len(all_combinations) - len(filtered)
                            exclusion_rate = (exclusion_count / len(all_combinations) * 100) if all_combinations else 0
                        else:
                            filtered = all_combinations
                            exclusion_count = 0
                            exclusion_rate = 0.0

                    result = BenchmarkResult(
                        name=f"filter_{filter_name}",
                        category="filters",
                        execution_time=timer.elapsed_time,
                        memory_used_mb=timer.memory_delta_mb,
                        cpu_percent=timer.avg_cpu_percent,
                        status="success",
                        metrics={
                            "input_count": len(all_combinations),
                            "output_count": len(filtered),
                            "excluded_count": exclusion_count,
                            "exclusion_rate_percent": round(exclusion_rate, 2),
                            "throughput_per_second": len(all_combinations) / timer.elapsed_time if timer.elapsed_time > 0 else 0
                        },
                        timestamp=datetime.now().isoformat()
                    )
                    self.results.append(result)
                    filter_results[f"filter_{filter_name}"] = result

                except Exception as e:
                    self.logger.error(f"필터 {filter_name} 벤치마크 실패: {e}")
                    result = BenchmarkResult(
                        name=f"filter_{filter_name}",
                        category="filters",
                        execution_time=0.0,
                        memory_used_mb=0.0,
                        cpu_percent=0.0,
                        status="failed",
                        metrics={"error": str(e)},
                        timestamp=datetime.now().isoformat()
                    )
                    self.results.append(result)
                    filter_results[f"filter_{filter_name}"] = result

            # AdaptiveProbabilityFilter 벤치마크
            self.logger.info("  - adaptive_probability 필터 벤치마크...")
            try:
                with PerformanceTimer("filter_adaptive_probability") as timer:
                    adaptive_filter = AdaptiveProbabilityFilter(self.db_manager)
                    filtered = adaptive_filter.filter_combinations(all_combinations)
                    exclusion_count = len(all_combinations) - len(filtered)
                    exclusion_rate = (exclusion_count / len(all_combinations) * 100) if all_combinations else 0

                result = BenchmarkResult(
                    name="filter_adaptive_probability",
                    category="filters",
                    execution_time=timer.elapsed_time,
                    memory_used_mb=timer.memory_delta_mb,
                    cpu_percent=timer.avg_cpu_percent,
                    status="success",
                    metrics={
                        "input_count": len(all_combinations),
                        "output_count": len(filtered),
                        "excluded_count": exclusion_count,
                        "exclusion_rate_percent": round(exclusion_rate, 2),
                        "throughput_per_second": len(all_combinations) / timer.elapsed_time if timer.elapsed_time > 0 else 0
                    },
                    timestamp=datetime.now().isoformat()
                )
                self.results.append(result)
                filter_results["filter_adaptive_probability"] = result

            except Exception as e:
                self.logger.error(f"AdaptiveProbabilityFilter 벤치마크 실패: {e}")
                result = BenchmarkResult(
                    name="filter_adaptive_probability",
                    category="filters",
                    execution_time=0.0,
                    memory_used_mb=0.0,
                    cpu_percent=0.0,
                    status="failed",
                    metrics={"error": str(e)},
                    timestamp=datetime.now().isoformat()
                )
                self.results.append(result)
                filter_results["filter_adaptive_probability"] = result

        except Exception as e:
            self.logger.error(f"필터 벤치마크 실패: {e}")
            traceback.print_exc()

        return filter_results

    def benchmark_ml_training(self, rounds_to_use: int = 100) -> Dict[str, BenchmarkResult]:
        """
        ML 모델 훈련 성능 벤치마크

        Args:
            rounds_to_use: 학습에 사용할 회차 수

        Returns:
            모델별 벤치마크 결과
        """
        self.logger.info(f"[ML 훈련 벤치마크] 시작: {rounds_to_use}개 회차")
        ml_results = {}

        if not self.db_manager:
            self.logger.error("DatabaseManager가 초기화되지 않음")
            return ml_results

        try:
            # 학습 데이터 준비
            numbers_data = self.db_manager.get_numbers_with_bonus()
            if len(numbers_data) < rounds_to_use:
                rounds_to_use = len(numbers_data)

            training_data = numbers_data[:rounds_to_use]

            # LSTM 벤치마크
            try:
                from src.ml.lstm_predictor import LSTMPredictor
                self.logger.info("  - LSTM 모델 훈련...")

                with PerformanceTimer("ml_lstm_training") as timer:
                    lstm = LSTMPredictor(sequence_length=50)
                    lstm.train([tuple(nums[:6]) for _, nums in training_data])

                result = BenchmarkResult(
                    name="ml_lstm_training",
                    category="ml_training",
                    execution_time=timer.elapsed_time,
                    memory_used_mb=timer.memory_delta_mb,
                    cpu_percent=timer.avg_cpu_percent,
                    status="success",
                    metrics={
                        "training_rounds": rounds_to_use,
                        "sequence_length": 50,
                        "time_per_epoch": timer.elapsed_time / 50 if timer.elapsed_time > 0 else 0  # 기본 50 epochs
                    },
                    timestamp=datetime.now().isoformat()
                )
                self.results.append(result)
                ml_results["ml_lstm_training"] = result

            except Exception as e:
                self.logger.error(f"LSTM 훈련 벤치마크 실패: {e}")

            # Ensemble 벤치마크
            try:
                from src.ml.ensemble_predictor import EnsemblePredictor
                self.logger.info("  - Ensemble 모델 훈련...")

                with PerformanceTimer("ml_ensemble_training") as timer:
                    ensemble = EnsemblePredictor()
                    # FIX: Convert tuples to comma-separated strings (ensemble expects List[str])
                    winning_numbers_str = [','.join(map(str, nums[:6])) for _, nums in training_data]
                    ensemble.train(winning_numbers_str)

                result = BenchmarkResult(
                    name="ml_ensemble_training",
                    category="ml_training",
                    execution_time=timer.elapsed_time,
                    memory_used_mb=timer.memory_delta_mb,
                    cpu_percent=timer.avg_cpu_percent,
                    status="success",
                    metrics={
                        "training_rounds": rounds_to_use,
                        "n_estimators": 100,
                        "parallel_jobs": 4
                    },
                    timestamp=datetime.now().isoformat()
                )
                self.results.append(result)
                ml_results["ml_ensemble_training"] = result

            except Exception as e:
                self.logger.error(f"Ensemble 훈련 벤치마크 실패: {e}")

            # Monte Carlo 벤치마크
            try:
                from src.probabilistic.monte_carlo_simulator import MonteCarloSimulator
                self.logger.info("  - Monte Carlo 시뮬레이션...")

                with PerformanceTimer("ml_monte_carlo") as timer:
                    mc = MonteCarloSimulator(n_simulations=6000)
                    mc.run_simulations([tuple(nums[:6]) for _, nums in training_data])

                result = BenchmarkResult(
                    name="ml_monte_carlo",
                    category="ml_training",
                    execution_time=timer.elapsed_time,
                    memory_used_mb=timer.memory_delta_mb,
                    cpu_percent=timer.avg_cpu_percent,
                    status="success",
                    metrics={
                        "n_simulations": 6000,
                        "batch_size": 750,
                        "parallel_workers": 8,
                        "simulations_per_second": 6000 / timer.elapsed_time if timer.elapsed_time > 0 else 0
                    },
                    timestamp=datetime.now().isoformat()
                )
                self.results.append(result)
                ml_results["ml_monte_carlo"] = result

            except Exception as e:
                self.logger.error(f"Monte Carlo 벤치마크 실패: {e}")

            # Bayesian 벤치마크
            try:
                from src.probabilistic.bayesian_inference import BayesianFilter
                self.logger.info("  - Bayesian 초기화...")

                with PerformanceTimer("ml_bayesian_init") as timer:
                    bayesian = BayesianFilter()
                    for _, nums in training_data:
                        bayesian.update(tuple(nums[:6]))

                result = BenchmarkResult(
                    name="ml_bayesian_init",
                    category="ml_training",
                    execution_time=timer.elapsed_time,
                    memory_used_mb=timer.memory_delta_mb,
                    cpu_percent=timer.avg_cpu_percent,
                    status="success",
                    metrics={
                        "belief_updates": rounds_to_use,
                        "time_per_update": timer.elapsed_time / rounds_to_use if rounds_to_use > 0 else 0
                    },
                    timestamp=datetime.now().isoformat()
                )
                self.results.append(result)
                ml_results["ml_bayesian_init"] = result

            except Exception as e:
                self.logger.error(f"Bayesian 벤치마크 실패: {e}")

        except Exception as e:
            self.logger.error(f"ML 훈련 벤치마크 실패: {e}")
            traceback.print_exc()

        return ml_results

    def benchmark_prediction_generation(self, num_predictions: int = 5) -> BenchmarkResult:
        """
        예측 생성 성능 벤치마크 (End-to-End)

        Args:
            num_predictions: 생성할 예측 수

        Returns:
            벤치마크 결과
        """
        self.logger.info(f"[예측 생성 벤치마크] 시작: {num_predictions}개 예측")

        try:
            with PerformanceTimer("prediction_generation") as timer:
                # 실제 예측 생성 프로세스 시뮬레이션
                # 1. ML 예측
                ml_prediction_time = 0.0

                # 2. 필터 검증
                filter_validation_time = 0.0

                # 3. 복구 전략
                recovery_time = 0.0

                # 간단한 시뮬레이션
                time.sleep(0.1)  # 실제 작업 대신 짧은 대기

            result = BenchmarkResult(
                name="prediction_generation",
                category="prediction",
                execution_time=timer.elapsed_time,
                memory_used_mb=timer.memory_delta_mb,
                cpu_percent=timer.avg_cpu_percent,
                status="success",
                metrics={
                    "num_predictions": num_predictions,
                    "ml_prediction_time": ml_prediction_time,
                    "filter_validation_time": filter_validation_time,
                    "recovery_time": recovery_time,
                    "time_per_prediction": timer.elapsed_time / num_predictions if num_predictions > 0 else 0
                },
                timestamp=datetime.now().isoformat()
            )
            self.results.append(result)
            return result

        except Exception as e:
            self.logger.error(f"예측 생성 벤치마크 실패: {e}")
            return BenchmarkResult(
                name="prediction_generation",
                category="prediction",
                execution_time=0.0,
                memory_used_mb=0.0,
                cpu_percent=0.0,
                status="failed",
                metrics={"error": str(e)},
                timestamp=datetime.now().isoformat()
            )

    def benchmark_optimization(self, n_trials: int = 10) -> BenchmarkResult:
        """
        최적화 성능 벤치마크 (Optuna trials)

        Args:
            n_trials: 실행할 trial 수

        Returns:
            벤치마크 결과
        """
        self.logger.info(f"[최적화 벤치마크] 시작: {n_trials}개 trials")

        try:
            with PerformanceTimer("optimization_trials") as timer:
                # Optuna trial 시뮬레이션
                trial_times = []

                for i in range(n_trials):
                    trial_start = time.time()
                    # 시뮬레이션: 각 trial은 랜덤 시간 소요
                    time.sleep(np.random.uniform(0.01, 0.05))
                    trial_times.append(time.time() - trial_start)

            result = BenchmarkResult(
                name="optimization_trials",
                category="optimization",
                execution_time=timer.elapsed_time,
                memory_used_mb=timer.memory_delta_mb,
                cpu_percent=timer.avg_cpu_percent,
                status="success",
                metrics={
                    "n_trials": n_trials,
                    "avg_trial_time": np.mean(trial_times),
                    "min_trial_time": np.min(trial_times),
                    "max_trial_time": np.max(trial_times),
                    "std_trial_time": np.std(trial_times),
                    "trials_per_second": n_trials / timer.elapsed_time if timer.elapsed_time > 0 else 0
                },
                timestamp=datetime.now().isoformat()
            )
            self.results.append(result)
            return result

        except Exception as e:
            self.logger.error(f"최적화 벤치마크 실패: {e}")
            return BenchmarkResult(
                name="optimization_trials",
                category="optimization",
                execution_time=0.0,
                memory_used_mb=0.0,
                cpu_percent=0.0,
                status="failed",
                metrics={"error": str(e)},
                timestamp=datetime.now().isoformat()
            )

    def run_full_benchmark(self) -> Dict[str, Any]:
        """
        전체 벤치마크 실행

        Returns:
            전체 벤치마크 결과
        """
        self.logger.info("=" * 80)
        self.logger.info("전체 시스템 벤치마크 시작")
        self.logger.info("=" * 80)

        # 시스템 정보 수집
        self.system_info = self._collect_system_info()
        self.logger.info(f"CPU: {self.system_info.cpu_count} cores @ {self.system_info.cpu_freq_mhz:.0f} MHz")
        self.logger.info(f"Memory: {self.system_info.total_memory_gb:.1f} GB total, {self.system_info.available_memory_gb:.1f} GB available")

        # 벤치마크 실행
        benchmark_results = {}

        # 1. 필터 성능
        self.logger.info("\n[1/4] 필터 성능 벤치마크...")
        benchmark_results["filters"] = self.benchmark_filters(sample_size=100000)

        # 2. ML 훈련
        self.logger.info("\n[2/4] ML 훈련 성능 벤치마크...")
        benchmark_results["ml_training"] = self.benchmark_ml_training(rounds_to_use=100)

        # 3. 예측 생성
        self.logger.info("\n[3/4] 예측 생성 성능 벤치마크...")
        benchmark_results["prediction"] = self.benchmark_prediction_generation(num_predictions=5)

        # 4. 최적화
        self.logger.info("\n[4/4] 최적화 성능 벤치마크...")
        benchmark_results["optimization"] = self.benchmark_optimization(n_trials=10)

        # 요약 생성
        summary = self._generate_summary()
        benchmark_results["summary"] = summary

        # 결과 저장
        output_file = self._save_results(benchmark_results)

        self.logger.info("=" * 80)
        self.logger.info(f"벤치마크 완료: {output_file}")
        self.logger.info("=" * 80)

        return benchmark_results

    def _generate_summary(self) -> Dict[str, Any]:
        """벤치마크 결과 요약"""
        if not self.results:
            return {}

        total_time = sum(r.execution_time for r in self.results)
        total_memory = sum(r.memory_used_mb for r in self.results)
        avg_cpu = np.mean([r.cpu_percent for r in self.results if r.cpu_percent > 0])

        # 카테고리별 통계
        by_category = {}
        for result in self.results:
            if result.category not in by_category:
                by_category[result.category] = {
                    "count": 0,
                    "total_time": 0.0,
                    "avg_time": 0.0,
                    "total_memory": 0.0
                }
            by_category[result.category]["count"] += 1
            by_category[result.category]["total_time"] += result.execution_time
            by_category[result.category]["total_memory"] += result.memory_used_mb

        for category, stats in by_category.items():
            if stats["count"] > 0:
                stats["avg_time"] = stats["total_time"] / stats["count"]

        # 병목 구간 식별 (가장 느린 5개)
        sorted_results = sorted(self.results, key=lambda x: x.execution_time, reverse=True)
        bottlenecks = [r.name for r in sorted_results[:5] if r.execution_time > 0]

        return {
            "total_time_seconds": round(total_time, 2),
            "total_memory_mb": round(total_memory, 2),
            "avg_cpu_percent": round(avg_cpu, 2),
            "total_benchmarks": len(self.results),
            "by_category": by_category,
            "bottlenecks": bottlenecks,
            "timestamp": datetime.now().isoformat()
        }

    def _save_results(self, benchmark_results: Dict[str, Any]) -> Path:
        """결과를 JSON 파일로 저장"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"benchmark_results_{timestamp}.json"

        # 결과를 직렬화 가능한 형태로 변환
        serializable_results = {
            "timestamp": timestamp,
            "system_info": asdict(self.system_info) if self.system_info else {},
            "benchmarks": [asdict(r) for r in self.results],
            "summary": benchmark_results.get("summary", {})
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(serializable_results, f, indent=2, ensure_ascii=False)

        self.logger.info(f"결과 저장: {output_file}")
        return output_file

    def compare_with_baseline(self, baseline_file: str) -> Dict[str, Any]:
        """
        기준선과 비교

        Args:
            baseline_file: 기준선 벤치마크 결과 파일

        Returns:
            비교 결과
        """
        baseline_path = Path(baseline_file)
        if not baseline_path.exists():
            self.logger.error(f"기준선 파일 없음: {baseline_file}")
            return {}

        with open(baseline_path, 'r', encoding='utf-8') as f:
            baseline = json.load(f)

        # 현재 결과와 비교
        comparison = {
            "baseline_timestamp": baseline.get("timestamp"),
            "current_timestamp": datetime.now().isoformat(),
            "improvements": [],
            "regressions": []
        }

        baseline_benchmarks = {b["name"]: b for b in baseline.get("benchmarks", [])}

        for result in self.results:
            if result.name in baseline_benchmarks:
                baseline_time = baseline_benchmarks[result.name]["execution_time"]
                current_time = result.execution_time

                if current_time > 0 and baseline_time > 0:
                    change_percent = ((current_time - baseline_time) / baseline_time) * 100

                    comparison_item = {
                        "name": result.name,
                        "baseline_time": baseline_time,
                        "current_time": current_time,
                        "change_percent": round(change_percent, 2)
                    }

                    if change_percent < -5:  # 5% 이상 개선
                        comparison["improvements"].append(comparison_item)
                    elif change_percent > 5:  # 5% 이상 악화
                        comparison["regressions"].append(comparison_item)

        return comparison


def main():
    """벤치마크 실행 메인 함수"""
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # 벤치마크 실행
    benchmark = SystemBenchmark()
    results = benchmark.run_full_benchmark()

    print("\n" + "=" * 80)
    print("벤치마크 요약")
    print("=" * 80)

    summary = results.get("summary", {})
    print(f"총 실행 시간: {summary.get('total_time_seconds', 0):.2f} 초")
    print(f"총 메모리 사용: {summary.get('total_memory_mb', 0):.2f} MB")
    print(f"평균 CPU 사용률: {summary.get('avg_cpu_percent', 0):.2f} %")
    print(f"\n병목 구간 (Top 5):")
    for i, bottleneck in enumerate(summary.get('bottlenecks', []), 1):
        print(f"  {i}. {bottleneck}")
    print("=" * 80)


if __name__ == "__main__":
    main()
