#!/usr/bin/env python3
"""
대시보드 기능 테스트 스크립트
Playwright를 사용하여 대시보드가 실제 백테스팅 데이터를 정상적으로 표시하는지 테스트
"""

import asyncio
import subprocess
import time
import requests
from playwright.async_api import async_playwright
import json
import sys
import os

# 프로젝트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

class DashboardTester:
    def __init__(self):
        self.dashboard_url = "http://127.0.0.1:5001"
        self.dashboard_process = None

    async def start_dashboard(self):
        """대시보드 서버 시작"""
        print(">> 대시보드 서버 시작 중...")

        # 대시보드 스크립트 실행
        self.dashboard_process = subprocess.Popen([
            sys.executable, "-c",
            """
import sys, os
sys.path.append('.')
from src.scripts.enhanced_dashboard_v2 import run_enhanced_dashboard_v2
run_enhanced_dashboard_v2(host='127.0.0.1', port=5001, debug=False)
            """
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=".")

        # 서버가 시작될 때까지 대기
        for attempt in range(30):  # 최대 30초 대기
            try:
                response = requests.get(f"{self.dashboard_url}/api/backtest-performance", timeout=5)
                if response.status_code == 200:
                    print("[OK] 대시보드 서버가 시작되었습니다.")
                    return True
            except requests.exceptions.RequestException:
                pass

            print(f"[WAIT] 서버 시작 대기 중... ({attempt + 1}/30)")
            time.sleep(1)

        print("[ERROR] 대시보드 서버 시작 실패")
        return False

    def stop_dashboard(self):
        """대시보드 서버 종료"""
        if self.dashboard_process:
            print("🛑 대시보드 서버 종료 중...")
            self.dashboard_process.terminate()
            try:
                self.dashboard_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.dashboard_process.kill()
                self.dashboard_process.wait()
            print("✅ 대시보드 서버가 종료되었습니다.")

    async def test_api_endpoints(self):
        """API 엔드포인트 테스트"""
        print("\n📡 API 엔드포인트 테스트 시작...")

        endpoints = [
            "/api/backtest-performance",
            "/api/stats",
            "/api/rounds"
        ]

        test_results = {}

        for endpoint in endpoints:
            try:
                response = requests.get(f"{self.dashboard_url}{endpoint}", timeout=10)
                data = response.json()

                print(f"✅ {endpoint}: {response.status_code}")

                # 백테스팅 성능 엔드포인트 특별 검증
                if endpoint == "/api/backtest-performance":
                    demo_mode = data.get('demo_mode', True)
                    available = data.get('available', False)

                    print(f"   • 데모 모드: {demo_mode}")
                    print(f"   • 데이터 사용 가능: {available}")

                    if not demo_mode and available:
                        print("   ✅ 실제 백테스팅 데이터를 사용하고 있습니다!")
                        test_results['backtest_real_data'] = True
                    else:
                        print("   ⚠️  데모 데이터를 사용하고 있습니다.")
                        test_results['backtest_real_data'] = False

                    # 성능 요약 데이터 검증
                    if 'performance_summary' in data:
                        summary = data['performance_summary']
                        if 'overall' in summary and 'by_model' in summary:
                            overall = summary['overall']
                            models = summary['by_model']
                            print(f"   • 총 예측: {overall.get('total_predictions', 0)}")
                            print(f"   • 모델 수: {len(models)}")
                            print(f"   • 평균 일치율: {overall.get('avg_match_rate', 0):.3f}")

                test_results[endpoint] = True

            except Exception as e:
                print(f"❌ {endpoint}: {str(e)}")
                test_results[endpoint] = False

        return test_results

    async def test_dashboard_ui(self):
        """대시보드 UI 테스트"""
        print("\n🖥️  대시보드 UI 테스트 시작...")

        async with async_playwright() as p:
            # 브라우저 시작 (headless=False로 설정하면 브라우저가 보임)
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                # 대시보드 페이지 로드
                print("📄 대시보드 페이지 로딩...")
                await page.goto(self.dashboard_url, timeout=30000)

                # 페이지 로드 대기
                await page.wait_for_load_state('domcontentloaded')
                await asyncio.sleep(3)  # 추가 로딩 시간

                # 페이지 제목 확인
                title = await page.title()
                print(f"✅ 페이지 제목: {title}")

                # 통계 로드 트리거 (showStatistics 함수 호출)
                print("📊 통계 데이터 로딩...")
                await page.evaluate("showStatistics()")
                await asyncio.sleep(5)  # 통계 로딩 대기

                # 백테스팅 성능 섹션 확인
                backtest_section = await page.query_selector("#backtestPerformance")
                if backtest_section:
                    is_visible = await backtest_section.is_visible()
                    print(f"✅ 백테스팅 성능 섹션 표시: {is_visible}")

                    # 데모 모드 알림 확인
                    demo_notice = await page.query_selector(".demo-notice")
                    if demo_notice:
                        is_demo_visible = await demo_notice.is_visible()
                        print(f"⚠️  데모 모드 알림 표시: {is_demo_visible}")
                        if is_demo_visible:
                            demo_text = await demo_notice.inner_text()
                            print(f"   데모 알림 내용: {demo_text[:100]}...")
                    else:
                        print("✅ 데모 모드 알림 없음 (실제 데이터 사용)")

                # 통계 카드들 확인
                stat_cards = await page.query_selector_all(".stat-card")
                print(f"✅ 통계 카드 수: {len(stat_cards)}")

                if stat_cards:
                    for i, card in enumerate(stat_cards[:4]):  # 처음 4개만 확인
                        value = await card.query_selector(".stat-value")
                        label = await card.query_selector(".stat-label")
                        if value and label:
                            value_text = await value.inner_text()
                            label_text = await label.inner_text()
                            print(f"   카드 {i+1}: {label_text} = {value_text}")

                # 스크린샷 저장
                screenshot_path = "dashboard_test_screenshot.png"
                await page.screenshot(path=screenshot_path, full_page=True)
                print(f"📸 스크린샷 저장: {screenshot_path}")

                print("✅ UI 테스트 완료")
                return True

            except Exception as e:
                print(f"❌ UI 테스트 실패: {str(e)}")
                return False

            finally:
                await browser.close()

    async def run_tests(self):
        """전체 테스트 실행"""
        print("🧪 대시보드 기능 테스트 시작")
        print("=" * 60)

        # 대시보드 서버 시작
        if not await self.start_dashboard():
            print("❌ 대시보드 서버 시작 실패 - 테스트 중단")
            return False

        try:
            # API 테스트
            api_results = await self.test_api_endpoints()

            # UI 테스트
            ui_result = await self.test_dashboard_ui()

            # 결과 요약
            print("\n" + "=" * 60)
            print("📋 테스트 결과 요약")
            print("=" * 60)

            total_tests = len(api_results) + 1  # API 테스트 + UI 테스트
            passed_tests = sum(api_results.values()) + (1 if ui_result else 0)

            print(f"총 테스트: {total_tests}")
            print(f"성공: {passed_tests}")
            print(f"실패: {total_tests - passed_tests}")

            # 백테스팅 데이터 상태 확인
            if api_results.get('backtest_real_data', False):
                print("\n✅ 성공: 대시보드가 실제 백테스팅 데이터를 표시하고 있습니다!")
            else:
                print("\n⚠️  경고: 대시보드가 여전히 데모 데이터를 사용하고 있습니다.")

            print("=" * 60)

            return passed_tests == total_tests

        finally:
            # 서버 종료
            self.stop_dashboard()

async def main():
    """메인 함수"""
    tester = DashboardTester()
    success = await tester.run_tests()

    if success:
        print("\n🎉 모든 테스트가 성공했습니다!")
        return 0
    else:
        print("\n❌ 일부 테스트가 실패했습니다.")
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️  테스트가 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 예상치 못한 오류: {e}")
        sys.exit(1)