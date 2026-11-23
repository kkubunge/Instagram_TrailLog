# TrailLog 두루누비 인스타그램 카드뉴스 자동 생성 및 게시기

한국관광공사 **두루누비 정보 서비스(`Durunubi`, Ver 4.1)** Open API와 실측 **GPX 경로·고도 데이터**, **국문 관광정보(`KorService2`) 실사 사진**을 활용해 인스타그램 피드용 **4:5(1080×1350px) 카드뉴스(최대 10장, 실사 사진 미연동 시 기본 5장)**, **AI 캡션/해시태그**, **모바일 미리보기 HTML**을 생성하고 **`@trailllog` 인스타그램 계정에 캐러셀 자동 업로드**까지 수행하는 **TrailLog** 프로젝트입니다.

API 데이터를 분석해 **숲·산 코스는 `forest`(아웃도어 포레스트)**, **바다·해안 코스는 `ocean`(오션 브리즈)** 컨셉을 자동으로 선택하며, GPX 지도 및 고도 차트 위에 스팟 포인트·라벨도 함께 표시합니다.

---

## 프로젝트 구조

- `config.py`: `.env` 로드, `TrailLog` 브랜드(`@trailllog`), 걷기/자전거·시도 코드 매핑, 크로스플랫폼 한글 폰트·SSL 세션 설정
- `durunubi_api.py`: 두루누비 `routeList` / `courseList` 조회 및 `gpxpath` XML 좌표·고도 파서
- `tour_photo_api.py`: 한국관광공사 국문 관광정보(`KorService2`) 기반 코스·스팟 실사 사진 및 GPS 좌표 수집
- `theme_selector.py`: 두루누비 API 메타데이터·설명·스팟 텍스트 기반 `forest` / `ocean` 자동 테마 판별
- `caption_writer.py`: Gemini API 기반 인스타그램 카피·캡션·해시태그 생성(검증된 폴백 모델 체인 포함)
- `card_common.py`: 공통 텍스트 줄바꿈·배지·GPX+스팟 투영·겹침 방지 라벨·고도 차트 유틸리티
- `card_renderer.py`: 스타일 레지스트리(`forest`, `ocean`) 및 아웃도어 포레스트(`forest`) 렌더러
- `style_ocean.py`: 오션 브리즈(`ocean`) 렌더러 (하늘빛 & 딥 오션 블루)
- `preview_builder.py`: 모바일 인스타그램 UI 미리보기 및 2종 스타일 비교 HTML(`style_compare.html`) 생성
- `instagram_publisher.py`: GitHub `media-assets` 공개 브랜치 이미지 호스팅 + Meta Instagram Graph API(`v24.0`) 캐러셀 자동 업로드 및 중복 방지 이력 관리
- `published_history.json`: 중복 게시 방지 및 일일 상한 집계용 게시 완료 코스 이력
- `main.py`: 생성·미리보기·자동 업로드·노선 순환·일일 상한 통합 CLI 진입점
- `.github/workflows/auto_publish.yml`: GitHub Actions 클라우드 무인 자동 발행 워크플로우

---

## GitHub Actions 무인 자동 발행 (매일 5회, PC 전원 불필요)

[auto_publish.yml](.github/workflows/auto_publish.yml)은 로컬 PC가 꺼져 있어도 GitHub 클라우드에서 매일 **09:00 · 11:00 · 13:00 · 15:00 · 17:00 (KST)** 에 미게시 코스 1건씩 자동 생성·업로드합니다.

- **Pretendard 폰트 자동 캐싱**: `Pretendard v1.3.9` TTF 3종을 캐싱해 로컬 PC와 동일한 카드뉴스 디자인 품질을 유지합니다.
- **노선 순환 (`--round-robin`)**: `DMZ 평화의 길` · `해파랑길` · `남파랑길` · `서해랑길`을 번갈아 선택해 `forest`와 `ocean` 테마가 균형 있게 올라갑니다.
- **일일 상한 (`--max-daily 5`)**: `published_history.json` 기준 당일(KST) 게시 건수가 5건에 도달하면 초과 발행 없이 안전하게 종료하고, 게시 완료 시 `published_history.json`을 `main`에 자동 커밋합니다.

### 최초 1회 설정 방법
1. 저장소 **Settings → Secrets and variables → Actions → New repository secret**에서 아래 4개 시크릿을 등록합니다.
   - `DURUNUBI_API_KEY`: 공공데이터포털 두루누비(및 KorService2) 인증키
   - `GEMINI_API_KEY`: Gemini API 키 (미설정 시 규칙 기반 폴백)
   - `IG_USER_ID`: 인스타그램 비즈니스 계정 ID (`17841426808330372`)
   - `IG_ACCESS_TOKEN`: Meta Graph API 액세스 토큰 (`instagram_content_publish` 권한 포함)
2. 저장소 **Actions → Auto Publish TrailLog Carousel → Run workflow**에서 `dry_run: true`로 1회 수동 테스트해 정상 동작을 확인합니다.

---

## 로컬 개발/수동 실행 예시

```powershell
# API 데이터 분석으로 숲/산(forest) 또는 바다(ocean) 자동 선택 생성 (미리보기 전용)
.\.venv\Scripts\python.exe main.py --brd 걷기 --count 1

# 숲·산(forest) 및 바다·해안(ocean) 2종 스타일 모두 생성하고 비교 페이지 보기
.\.venv\Scripts\python.exe main.py --brd 걷기 --style all --count 1

# 계정·일일 한도 및 GitHub 공개 저장소 연결 점검
.\.venv\Scripts\python.exe instagram_publisher.py --check

# 생성된 output 폴더 사전 검증 (드라이런) / 즉시 업로드
.\.venv\Scripts\python.exe instagram_publisher.py --dir output\T_CRS_MNG0000004239_해파랑길_1코스 --dry-run
.\.venv\Scripts\python.exe instagram_publisher.py --dir output\T_CRS_MNG0000004239_해파랑길_1코스

# 미게시 코스 1건을 노선 순환·일일 상한 적용해 생성부터 실제 게시까지 실행
.\.venv\Scripts\python.exe main.py --brd 걷기 --skip-published --round-robin --max-daily 5 --count 1 --publish
```
