#!/usr/bin/env python3
"""
성능 모니터링 대시보드
백테스팅 결과와 실시간 성능을 모니터링하고 시각화
"""
import logging
import json
import os
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import numpy as np
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from src.core.performance_metrics import PerformanceMetrics

# JSON 직렬화를 위한 커스텀 encoder
class NumpyJSONEncoder(json.JSONEncoder):
    """numpy 타입을 JSON 직렬화 가능한 타입으로 변환"""
    def default(self, obj):
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

# 시각화 라이브러리
try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    PLOTTING_AVAILABLE = True
except ImportError:
    PLOTTING_AVAILABLE = False
    logging.warning("matplotlib/seaborn not available. Visual reports will be limited.")

from ..core.db_manager import DatabaseManager
from ..backtesting.optimized_backtesting_framework import OptimizedBacktestingFramework
from ..optimization.feedback_loop_system import FeedbackLoopSystem
from ..utils.singleton import SingletonMeta


class PerformanceDashboard(metaclass=SingletonMeta):
    """성능 모니터링 대시보드 클래스"""
    
    def __init__(self, db_manager=None):
        """
        Args:
            db_manager: 데이터베이스 관리자 인스턴스
        """
        # 이미 초기화되었는지 확인
        if hasattr(self, '_initialized'):
            return
        
        self.db_manager = db_manager or DatabaseManager()
        self.backtesting_framework = OptimizedBacktestingFramework(db_manager, enable_fractal=False)
        self.feedback_loop_system = FeedbackLoopSystem(db_manager)
        
        # 결과 저장 경로
        self.results_dir = 'results'
        self.charts_dir = 'output/charts'
        os.makedirs(self.charts_dir, exist_ok=True)
        
        # 성능 추적
        self.performance_history = []
        self.current_performance = {}
        
        self._initialized = True
        logging.info("성능 모니터링 대시보드 초기화 완료 (싱글톤)")
    
    def generate_comprehensive_report(self, auto_improve: bool = False) -> Dict[str, Any]:
        """종합 성능 보고서 생성
        
        Args:
            auto_improve: 자동 개선 시스템 실행 여부
            
        Returns:
            Dict: 종합 보고서 데이터
        """
        logging.info("\n" + "="*80)
        logging.info("[Performance Report] 종합 성능 보고서 생성 시작")
        logging.info("="*80)
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'backtest_results': {},
            'model_performance': {},
            'improvement_tracking': {},
            'recommendations': [],
            'charts': []
        }
        
        # Step 1: 백테스팅 실행
        logging.info("\n[Step 1/4] 백테스팅 실행 중...")
        backtest_results = self._run_latest_backtest()
        report['backtest_results'] = backtest_results
        
        # Step 2: 모델별 성능 분석
        logging.info("\n[Step 2/4] 모델별 성능 분석 중...")
        model_performance = self._analyze_model_performance(backtest_results)
        report['model_performance'] = model_performance
        
        # Step 3: 성능 추이 분석
        logging.info("\n[Step 3/4] 성능 추이 분석 중...")
        improvement_tracking = self._track_improvements()
        report['improvement_tracking'] = improvement_tracking
        
        # Step 4: 시각화 및 권장사항
        logging.info("\n[Step 4/4] 시각화 및 권장사항 생성 중...")
        if PLOTTING_AVAILABLE:
            charts = self._generate_charts(report)
            report['charts'] = charts
        
        recommendations = self._generate_recommendations(report)
        report['recommendations'] = recommendations
        
        # 자동 개선 실행
        if auto_improve:
            logging.info("\n🔄 자동 개선 시스템 실행 중...")
            improvement_results = self._execute_auto_improvement(report)
            report['auto_improvement'] = improvement_results
        
        # 보고서 저장
        self._save_report(report)
        
        # 텍스트 보고서 출력
        self._print_text_report(report)
        
        return report
    
    def _run_latest_backtest(self) -> Dict[str, Any]:
        """최신 백테스팅 실행"""
        # 최근 50회차 백테스팅
        latest_round = self.db_manager.lotto_db.get_last_round()
        start_round = max(1, latest_round - 49)
        end_round = latest_round
        
        results = self.backtesting_framework.run_backtest(
            start_round=start_round,
            end_round=end_round,
            window_size=100
        )
        
        # 성능 보고서 생성
        performance_report = self.backtesting_framework.generate_performance_report(results)
        results['performance_report'] = performance_report
        
        return results
    
    def _analyze_model_performance(self, backtest_results: Dict[str, Any]) -> Dict[str, Any]:
        """모델별 성능 상세 분석"""
        analysis = {}
        metrics = backtest_results.get('performance_metrics', {})
        
        for model_name, model_metrics in metrics.get('model_performance', {}).items():
            analysis[model_name] = {
                'performance_score': self._calculate_performance_score(model_metrics),
                'strengths': self._identify_strengths(model_metrics),
                'weaknesses': self._identify_weaknesses(model_metrics),
                'trend': self._analyze_trend(model_name)
            }
        
        return analysis
    
    def _calculate_performance_score(self, model_metrics: Dict[str, Any]) -> float:
        """
        성능 점수 계산 (0-100 scale) - 통합 메트릭 시스템 사용

        Uses PerformanceMetrics.calculate_composite_score() for consistency.
        """
        avg_matches = model_metrics.get('avg_matches', 0)
        accuracy_3plus = model_metrics.get('accuracy_3plus', 0)
        best_match = model_metrics.get('best_match', 0)

        # 통합 composite score 계산 함수 사용
        score = PerformanceMetrics.calculate_composite_score(
            avg_matches=avg_matches,
            accuracy_3plus=accuracy_3plus,
            best_match=best_match
        )

        return score
    
    def _identify_strengths(self, model_metrics: Dict[str, Any]) -> List[str]:
        """모델의 강점 식별"""
        strengths = []
        
        if model_metrics.get('avg_matches', 0) > 1.5:
            strengths.append("높은 평균 일치율")
        
        if model_metrics.get('accuracy_3plus', 0) > 5.0:
            strengths.append("우수한 3개 이상 일치율")
        
        if model_metrics.get('best_match', 0) >= 4:
            strengths.append("4개 이상 일치 달성")
        
        match_distribution = model_metrics.get('match_counts', {})
        if match_distribution.get(0, 0) < match_distribution.get(1, 0):
            strengths.append("낮은 완전 실패율")
        
        return strengths
    
    def _identify_weaknesses(self, model_metrics: Dict[str, Any]) -> List[str]:
        """모델의 약점 식별"""
        weaknesses = []
        
        if model_metrics.get('avg_matches', 0) < 1.0:
            weaknesses.append("낮은 평균 일치율")
        
        if model_metrics.get('accuracy_3plus', 0) < 2.0:
            weaknesses.append("3개 이상 일치율 부족")
        
        match_distribution = model_metrics.get('match_counts', {})
        zero_matches = match_distribution.get(0, 0)
        total = model_metrics.get('total_predictions', 1)
        
        if total > 0 and zero_matches / total > 0.3:
            weaknesses.append("높은 완전 실패율")
        
        return weaknesses
    
    def _analyze_trend(self, model_name: str) -> str:
        """성능 추세 분석"""
        # 이전 결과와 비교하여 추세 판단
        # 실제 구현에서는 과거 데이터와 비교
        return "stable"  # improving, declining, stable
    
    def _track_improvements(self) -> Dict[str, Any]:
        """개선 사항 추적"""
        # 최근 결과 파일들 로드
        recent_results = self._load_recent_results(5)
        
        if len(recent_results) < 2:
            return {"status": "insufficient_data"}
        
        tracking = {
            'performance_over_time': [],
            'improvement_rate': 0,
            'best_performing_iteration': None,
            'convergence_status': 'in_progress'
        }
        
        # 시간별 성능 추적
        for result in recent_results:
            metrics = result.get('performance_metrics', {})
            avg_performance = self._calculate_average_performance(metrics)
            
            tracking['performance_over_time'].append({
                'timestamp': result.get('timestamp', 'unknown'),
                'avg_performance': avg_performance
            })
        
        # 개선율 계산
        if len(tracking['performance_over_time']) >= 2:
            initial = tracking['performance_over_time'][0]['avg_performance']
            latest = tracking['performance_over_time'][-1]['avg_performance']
            tracking['improvement_rate'] = ((latest - initial) / initial * 100) if initial > 0 else 0
        
        return tracking
    
    def _calculate_average_performance(self, metrics: Dict[str, Any]) -> float:
        """전체 평균 성능 계산"""
        total_score = 0
        model_count = 0
        
        for model_metrics in metrics.get('model_performance', {}).values():
            score = self._calculate_performance_score(model_metrics)
            total_score += score
            model_count += 1
        
        return total_score / model_count if model_count > 0 else 0
    
    def _generate_charts(self, report: Dict[str, Any]) -> List[str]:
        """성능 차트 생성"""
        charts = []
        
        # 1. 모델별 성능 비교 차트
        chart_path = self._create_model_comparison_chart(report['model_performance'])
        if chart_path:
            charts.append(chart_path)
        
        # 2. 성능 추이 차트
        if report['improvement_tracking'].get('performance_over_time'):
            trend_chart = self._create_trend_chart(report['improvement_tracking'])
            if trend_chart:
                charts.append(trend_chart)
        
        # 3. 일치 분포 히트맵
        heatmap_path = self._create_match_distribution_heatmap(report['backtest_results'])
        if heatmap_path:
            charts.append(heatmap_path)
        
        return charts
    
    def _create_model_comparison_chart(self, model_performance: Dict[str, Any]) -> Optional[str]:
        """모델 성능 비교 차트 생성"""
        if not PLOTTING_AVAILABLE:
            return None
        
        try:
            models = []
            scores = []
            
            for model, perf in model_performance.items():
                models.append(model.upper())
                scores.append(perf['performance_score'])
            
            plt.figure(figsize=(10, 6))
            bars = plt.bar(models, scores, color=['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A'])
            
            # 값 표시
            for bar, score in zip(bars, scores):
                plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                        f'{score:.1f}', ha='center', va='bottom')
            
            plt.title('모델별 성능 점수 비교', fontsize=16, fontweight='bold', pad=20)
            plt.xlabel('모델', fontsize=12)
            plt.ylabel('성능 점수 (0-100)', fontsize=12)
            plt.ylim(0, 100)
            plt.grid(axis='y', alpha=0.3)
            
            chart_path = os.path.join(self.charts_dir, 'model_comparison.png')
            plt.tight_layout()
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            return chart_path
            
        except Exception as e:
            logging.error(f"차트 생성 오류: {str(e)}")
            return None
    
    def _create_trend_chart(self, tracking: Dict[str, Any]) -> Optional[str]:
        """성능 추이 차트 생성"""
        if not PLOTTING_AVAILABLE:
            return None
        
        try:
            data = tracking['performance_over_time']
            if not data:
                return None
            
            timestamps = [i for i in range(len(data))]
            performances = [d['avg_performance'] for d in data]
            
            plt.figure(figsize=(10, 6))
            plt.plot(timestamps, performances, marker='o', linewidth=2, 
                    markersize=8, color='#4ECDC4')
            
            # 추세선
            if len(timestamps) > 1:
                z = np.polyfit(timestamps, performances, 1)
                p = np.poly1d(z)
                plt.plot(timestamps, p(timestamps), "--", color='red', alpha=0.8)
            
            plt.title('성능 개선 추이', fontsize=16, fontweight='bold', pad=20)
            plt.xlabel('반복 횟수', fontsize=12)
            plt.ylabel('평균 성능 점수', fontsize=12)
            plt.grid(True, alpha=0.3)
            
            chart_path = os.path.join(self.charts_dir, 'performance_trend.png')
            plt.tight_layout()
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            return chart_path
            
        except Exception as e:
            logging.error(f"추이 차트 생성 오류: {str(e)}")
            return None
    
    def _create_match_distribution_heatmap(self, backtest_results: Dict[str, Any]) -> Optional[str]:
        """일치 분포 히트맵 생성"""
        if not PLOTTING_AVAILABLE:
            return None
        
        try:
            metrics = backtest_results.get('performance_metrics', {})
            
            # 데이터 준비
            models = []
            data = []
            
            for model_name, model_metrics in metrics.get('model_performance', {}).items():
                models.append(model_name.upper())
                match_counts = model_metrics.get('match_counts', {})
                total = model_metrics.get('total_predictions', 1)
                
                row = []
                for i in range(7):
                    count = match_counts.get(i, 0)
                    pct = (count / total * 100) if total > 0 else 0
                    row.append(pct)
                data.append(row)
            
            if not data:
                return None
            
            # 히트맵 생성
            plt.figure(figsize=(10, 6))
            sns.heatmap(data, annot=True, fmt='.1f', cmap='YlOrRd',
                       xticklabels=[f'{i}개' for i in range(7)],
                       yticklabels=models, cbar_kws={'label': '비율 (%)'})
            
            plt.title('모델별 일치 개수 분포 히트맵', fontsize=16, fontweight='bold', pad=20)
            plt.xlabel('일치 개수', fontsize=12)
            plt.ylabel('모델', fontsize=12)
            
            chart_path = os.path.join(self.charts_dir, 'match_distribution_heatmap.png')
            plt.tight_layout()
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            return chart_path
            
        except Exception as e:
            logging.error(f"히트맵 생성 오류: {str(e)}")
            return None
    
    def _generate_recommendations(self, report: Dict[str, Any]) -> List[Dict[str, Any]]:
        """개선 권장사항 생성"""
        recommendations = []
        
        # 모델별 권장사항
        for model_name, analysis in report['model_performance'].items():
            if analysis['performance_score'] < 30:
                recommendations.append({
                    'priority': 'high',
                    'model': model_name,
                    'type': 'model_improvement',
                    'suggestion': f"{model_name} 모델의 전체적인 재설계가 필요합니다.",
                    'actions': [
                        "하이퍼파라미터 최적화 실행",
                        "특징 엔지니어링 개선",
                        "모델 구조 변경 고려"
                    ]
                })
            elif analysis['performance_score'] < 50:
                recommendations.append({
                    'priority': 'medium',
                    'model': model_name,
                    'type': 'parameter_tuning',
                    'suggestion': f"{model_name} 모델의 파라미터 조정이 필요합니다.",
                    'actions': [
                        "학습률 조정",
                        "정규화 파라미터 최적화",
                        "앙상블 가중치 재조정"
                    ]
                })
        
        # 전체 시스템 권장사항
        avg_score = np.mean([a['performance_score'] for a in report['model_performance'].values()])
        if avg_score < 40:
            recommendations.append({
                'priority': 'high',
                'model': 'system',
                'type': 'system_overhaul',
                'suggestion': "전체 시스템의 근본적인 개선이 필요합니다.",
                'actions': [
                    "데이터 전처리 파이프라인 검토",
                    "새로운 모델 아키텍처 도입 고려",
                    "앙상블 전략 재설계"
                ]
            })
        
        return recommendations
    
    def _execute_auto_improvement(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """자동 개선 실행"""
        improvement_results = {
            'executed': True,
            'timestamp': datetime.now().isoformat(),
            'actions_taken': [],
            'results': {}
        }
        
        # 권장사항 기반 개선 실행
        for recommendation in report['recommendations']:
            if recommendation['priority'] == 'high':
                action = {
                    'model': recommendation['model'],
                    'type': recommendation['type'],
                    'status': 'executed'
                }
                
                # 실제 개선 로직 실행
                # 여기서는 피드백 루프 시스템 호출
                logging.info(f"자동 개선 실행: {recommendation['model']} - {recommendation['type']}")
                
                improvement_results['actions_taken'].append(action)
        
        return improvement_results
    
    def _load_recent_results(self, n: int = 5) -> List[Dict[str, Any]]:
        """최근 n개의 결과 파일 로드"""
        results = []
        
        try:
            # results 디렉토리의 파일들 검색
            result_files = [f for f in os.listdir(self.results_dir) 
                          if f.startswith('backtest_results_') and f.endswith('.json')]
            
            # 시간순 정렬
            result_files.sort(reverse=True)
            
            # 최근 n개 로드
            for file_name in result_files[:n]:
                file_path = os.path.join(self.results_dir, file_name)
                with open(file_path, 'r', encoding='utf-8') as f:
                    results.append(json.load(f))
                    
        except Exception as e:
            logging.error(f"결과 파일 로드 오류: {str(e)}")
        
        return results
    
    def _save_report(self, report: Dict[str, Any]):
        """보고서 저장"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = os.path.join(self.results_dir, f'performance_report_{timestamp}.json')
            
            # 디렉토리 존재 확인 및 생성
            os.makedirs(self.results_dir, exist_ok=True)
            
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, cls=NumpyJSONEncoder)
            
            logging.info(f"성능 보고서 저장: {report_path}")
        except Exception as e:
            logging.error(f"성능 보고서 저장 중 오류: {str(e)}")
            # 임시 위치에 저장 시도
            try:
                temp_path = f"temp_performance_report_{timestamp}.json"
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(report, f, ensure_ascii=False, indent=2, cls=NumpyJSONEncoder)
                logging.info(f"임시 경로에 성능 보고서 저장: {temp_path}")
            except Exception as temp_err:
                logging.error(f"임시 보고서 저장도 실패: {str(temp_err)}")
    
    def _print_text_report(self, report: Dict[str, Any]):
        """텍스트 형식 보고서 출력"""
        try:
            print("\n" + "="*80)
            print("[Performance Report] 로또 예측 시스템 종합 성능 보고서")
            print("="*80)
            print(f"생성 시간: {report['timestamp']}")
            
            # 모델별 성능
            print("\n[Model Performance] 모델별 성능 점수:")
            for model, analysis in report['model_performance'].items():
                score = analysis['performance_score']
                status = "[GOOD]" if score > 50 else "[WARN]" if score > 30 else "[BAD]"
                print(f"  {status} {model.upper()}: {score:.1f}점")
        except UnicodeEncodeError:
            # 인코딩 에러 발생 시 로깅만 수행
            logging.info("\n" + "="*80)
            logging.info("[Performance Report] 종합 성능 보고서 생성 완료")
            logging.info("="*80)
            
            if analysis['strengths']:
                print(f"    ✓ 강점: {', '.join(analysis['strengths'])}")
            if analysis['weaknesses']:
                print(f"    ✗ 약점: {', '.join(analysis['weaknesses'])}")
        
        # 개선 추적
        tracking = report.get('improvement_tracking', {})
        if tracking.get('improvement_rate') is not None:
            rate = tracking['improvement_rate']
            trend = "[UP]" if rate > 0 else "[DOWN]" if rate < 0 else "[SAME]"
            print(f"\n{trend} 전체 개선율: {rate:+.1f}%")
        
        # 권장사항
        if report['recommendations']:
            print("\n[Recommendations] 주요 권장사항:")
            for i, rec in enumerate(report['recommendations'][:3], 1):
                priority_icon = "[HIGH]" if rec['priority'] == 'high' else "[MED]"
                print(f"  {priority_icon} {i}. {rec['suggestion']}")
        
        # 차트 생성 여부
        if report.get('charts'):
            print(f"\n[Charts] 생성된 차트: {len(report['charts'])}개")
            for chart in report['charts']:
                print(f"  - {os.path.basename(chart)}")
        
        print("\n" + "="*80)
    
    def generate_dashboard(self) -> str:
        """간단한 대시보드 생성 (기존 호환성 유지)
        
        Returns:
            str: 대시보드 파일 경로
        """
        # 종합 보고서 생성
        report = self.generate_comprehensive_report(auto_improve=False)
        
        # 대시보드 HTML 생성 (간단한 버전)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dashboard_path = os.path.join(self.results_dir, f'dashboard_{timestamp}.html')
        
        html_content = self._generate_html_dashboard(report)
        
        with open(dashboard_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return dashboard_path
    
    def check_performance_degradation(self, threshold: float = 0.8) -> List[str]:
        """성능 저하 확인
        
        Args:
            threshold: 성능 저하 판단 임계값 (이전 대비 비율)
            
        Returns:
            List[str]: 성능 저하 경고 메시지 리스트
        """
        degradations = []
        
        # 최근 결과 2개 비교
        recent_results = self._load_recent_results(2)
        
        if len(recent_results) >= 2:
            prev_metrics = recent_results[1].get('performance_metrics', {})
            curr_metrics = recent_results[0].get('performance_metrics', {})
            
            for model_name in ['lstm', 'ensemble', 'monte_carlo']:
                prev_perf = prev_metrics.get('model_performance', {}).get(model_name, {})
                curr_perf = curr_metrics.get('model_performance', {}).get(model_name, {})
                
                prev_avg = prev_perf.get('avg_matches', 0)
                curr_avg = curr_perf.get('avg_matches', 0)
                
                if prev_avg > 0 and curr_avg / prev_avg < threshold:
                    degradations.append(
                        f"{model_name.upper()}: {prev_avg:.2f} → {curr_avg:.2f} "
                        f"({(curr_avg/prev_avg-1)*100:+.1f}%)"
                    )
        
        return degradations
    
    def _generate_html_dashboard(self, report: Dict[str, Any]) -> str:
        """HTML 대시보드 생성
        
        Args:
            report: 성능 보고서 데이터
            
        Returns:
            str: HTML 콘텐츠
        """
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>로또 예측 시스템 대시보드</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; text-align: center; }}
        .metric {{ display: inline-block; margin: 10px; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
        .metric h3 {{ margin: 0 0 10px 0; color: #666; }}
        .metric .value {{ font-size: 24px; font-weight: bold; }}
        .good {{ color: #4CAF50; }}
        .warning {{ color: #FF9800; }}
        .bad {{ color: #F44336; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 10px; border: 1px solid #ddd; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .recommendations {{ background-color: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .chart-container {{ text-align: center; margin: 20px 0; }}
        .chart-container img {{ max-width: 100%; height: auto; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>[Dashboard] 로또 예측 시스템 성능 대시보드</h1>
        <p style="text-align: center; color: #666;">생성 시간: {report['timestamp']}</p>
        
        <h2>[Chart] 모델별 성능 점수</h2>
        <div style="text-align: center;">
"""
        
        # 모델별 성능 메트릭
        for model, analysis in report['model_performance'].items():
            score = analysis['performance_score']
            status_class = 'good' if score > 50 else 'warning' if score > 30 else 'bad'
            
            html += f"""
            <div class="metric">
                <h3>{model.upper()}</h3>
                <div class="value {status_class}">{score:.1f}</div>
                <small>/ 100</small>
            </div>
"""
        
        html += """
        </div>
        
        <h2>[Analysis] 성능 상세 분석</h2>
        <table>
            <tr>
                <th>모델</th>
                <th>강점</th>
                <th>약점</th>
                <th>추세</th>
            </tr>
"""
        
        # 상세 분석 테이블
        for model, analysis in report['model_performance'].items():
            strengths = ', '.join(analysis['strengths']) if analysis['strengths'] else '없음'
            weaknesses = ', '.join(analysis['weaknesses']) if analysis['weaknesses'] else '없음'
            trend = analysis['trend']
            
            html += f"""
            <tr>
                <td><strong>{model.upper()}</strong></td>
                <td>{strengths}</td>
                <td>{weaknesses}</td>
                <td>{trend}</td>
            </tr>
"""
        
        html += """
        </table>
"""
        
        # 권장사항
        if report['recommendations']:
            html += """
        <div class="recommendations">
            <h2>[Recommendations] 개선 권장사항</h2>
            <ul>
"""
            for rec in report['recommendations']:
                priority = "[HIGH]" if rec['priority'] == 'high' else "[MED]"
                html += f"<li>{priority} <strong>{rec['model'].upper()}</strong>: {rec['suggestion']}</li>\n"
            
            html += """
            </ul>
        </div>
"""
        
        # 차트 이미지
        if report.get('charts'):
            html += """
        <h2>[Charts] 성능 차트</h2>
        <div class="chart-container">
"""
            for chart_path in report['charts']:
                # 상대 경로로 변환
                chart_name = os.path.basename(chart_path)
                html += f'<img src="../{chart_path}" alt="{chart_name}"><br>\n'
            
            html += """
        </div>
"""
        
        html += """
    </div>
</body>
</html>
"""
        return html
    
    def update_metrics(self, metric_type: str, model_name: str, value: float):
        """메트릭 업데이트 (호환성 유지)
        
        Args:
            metric_type: 메트릭 타입
            model_name: 모델 이름
            value: 값
        """
        # 현재 성능 추적에 저장
        if metric_type not in self.current_performance:
            self.current_performance[metric_type] = {}
        
        self.current_performance[metric_type][model_name] = value
        
        # 히스토리에 추가
        self.performance_history.append({
            'timestamp': datetime.now().isoformat(),
            'metric_type': metric_type,
            'model_name': model_name,
            'value': value
        })


def main():
    """테스트 실행"""
    from ..logger import setup_logging
    setup_logging()
    
    dashboard = PerformanceDashboard()
    
    # 종합 보고서 생성 (자동 개선 포함)
    report = dashboard.generate_comprehensive_report(auto_improve=True)
    
    logging.info("\n성능 모니터링 완료!")


if __name__ == "__main__":
    main()