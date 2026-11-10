# JBNU 소프트웨어아키텍처설계 과제3 — 마이크로커널 아키텍처 스타일을 적용한 시스템 구현

202110914 김대진

- 제출 보고서: [`과제3-보고서.pdf`](과제3-보고서.pdf) — 진행 과정, 시스템 화면, 구조, 코어와 서버의 인터랙션, 품질 문제와 해결, 검증, 사용한 프롬프트
- 사용한 프롬프트: [`prompt.md`](prompt.md)

## 낸 시스템

`candidate-docconv/` — 문서 → Markdown 변환기. txt·html·docx·hwpx·pdf 를 Markdown 으로 바꾸는 로컬 웹 앱입니다. 형식별 변환기와 후처리기가 플러그인이고, 서버를 끄지 않고 플러그인을 설치·제거합니다.

```bash
cd candidate-docconv
python tools/make_samples.py     # samples/ 에 시연 자료 생성
python app.py                    # http://127.0.0.1:8802
python -B -m unittest discover -s tests
```

Python 3.14 표준 라이브러리만 씁니다. pdf 변환기만 PyMuPDF 를 씁니다. 자세한 사용법과 5분 시연 절차는 `candidate-docconv/README.md` 에 있습니다.

### 한 줄로 실행 (발표·시연용, Windows)

cmd 창이나 PowerShell 창에 아래 한 줄을 붙여 넣고 Enter 를 누릅니다. 바탕화면(없으면 사용자 폴더)에 저장소 ZIP 을 받아 `JBNU-SW_Architecture-HW3-main` 폴더에 풀고 `run.bat` 을 실행합니다. `run.bat` 은 Python·PyMuPDF 를 준비하고, 시연 자료를 만든 뒤 서버를 켜고 브라우저를 엽니다.

```
cmd /c "(cd /d %USERPROFILE%\Desktop 2>nul || cd /d %USERPROFILE%) && curl -fL -o hw3.zip https://github.com/Daejin8753/JBNU-SW_Architecture-HW3/archive/refs/heads/main.zip && tar -xf hw3.zip && del hw3.zip && JBNU-SW_Architecture-HW3-main\run.bat"
```

- Windows 10(1803 이후)·11 에 들어 있는 curl·tar 만 씁니다. 인터넷은 필요하고 관리자 권한은 필요 없습니다.
- Python 3.10 이상이 있으면 그것을 씁니다. 없으면 uv 로 Python 3.14 를 그 폴더 안에만 받습니다(약 190MB, 1~2분). PATH 는 바꾸지 않습니다.
- PyMuPDF 는 시험한 1.27.2.3 을 그 폴더의 `.run\venv` 에 설치합니다.
- 실행할 때마다 지난 시연 상태(`data/`, `plugins/csv_conv.py`)를 지우고 처음 상태로 시작합니다.
- 8802 포트가 쓰이고 있으면 다음 빈 포트를 쓰고, 화면에 주소를 보여 줍니다. 끄려면 그 창에서 Ctrl+C(일괄 작업 종료를 물으면 Y) 또는 창을 닫습니다.
- 저장소를 브라우저로 받았으면(Code → Download ZIP → 압축 풀기) 그 폴더의 `run.bat` 을 더블클릭해도 같습니다. 두 번째부터는 내려받기·설치를 건너뛰어 몇 초 안에 켜집니다.
- 스크립트를 받아 바로 실행하는 PowerShell 형태(`irm … | iex`)는 Microsoft Defender 가 악성 명령으로 막아서 쓰지 않습니다.

## 폴더

| 경로 | 내용 |
|---|---|
| `report.html`, `과제3-보고서.pdf` | 보고서(HTML 원본과 제출용 PDF) |
| `capture/` | 보고서에 넣은 화면 캡처 |
| `candidate-docconv/` | 낸 시스템(후보 B) |
| `candidate-auction/` | 비교용 후보 A 온라인 경매. 구현 검토 지적 10건을 고치지 않은 상태입니다(보고서 1.4) |
| `지시서/` | 구현 지시서(공통·A·B)와 교차 검토 13회 기록 |
| `run.ps1`, `run.bat` | 한 줄 실행 스크립트(내려받기·준비·실행) |
| `prompt.md` | 과제를 진행하며 한 지시를 순서대로 적은 기록(보고서 부록 A) |
| `과제2-회고.md` | 과제2 진행에서 부족했던 점과 이번에 바꾼 것 |

보고서 HTML 을 고치면 PDF 도 다시 만듭니다.
