# 과제3 실행 스크립트: 내려받기 · 준비 · 실행을 한 번에 한다. 어느 시스템을 켤지는 bat 이 HW3_APP 로 정한다.
#   run.bat         → 문서 → Markdown 변환기 (candidate-docconv, 제출한 시스템)
#   run-auction.bat → 온라인 경매 (candidate-auction, 비교용 후보 A)
#
# 한 줄 실행 (cmd 창, PowerShell 창 어디서나): 바탕화면(없으면 사용자 폴더)에 저장소 ZIP 을 받아 풀고 run.bat 을 실행한다.
#   cmd /c "(cd /d %USERPROFILE%\Desktop 2>nul || cd /d %USERPROFILE%) && curl -fL -o hw3.zip https://github.com/Daejin8753/JBNU-SW_Architecture-HW3/archive/refs/heads/main.zip && tar -xf hw3.zip && del hw3.zip && JBNU-SW_Architecture-HW3-main\run.bat"
# 경매는 위 줄 끝의 run.bat 을 run-auction.bat 으로 바꾼다. 이미 받은 폴더가 있으면 파일을 덮어쓰고 .run\venv 는 그대로 쓴다.
# 저장소를 이미 받아 둔 경우: 저장소 루트의 run.bat(또는 run-auction.bat)을 더블클릭한다.
# 스크립트를 받아 바로 실행하는 irm ... | iex 형태는 Microsoft Defender 가 악성 명령으로 막아서 쓰지 않는다.
# (이 파일은 BOM 없는 UTF-8 이다. Windows PowerShell 5.1 에서 .\run.ps1 로 직접 돌리면 한글이 깨지므로 bat 을 쓴다.)
#
# 하는 일
#   1. 폴더 준비: 이 파일이 저장소 안에 있으면 그 폴더를 쓴다. 이 파일만 따로 실행하면 바탕화면\JBNU-HW3 에 저장소 ZIP 을 받아 푼다.
#   2. Python 준비: 설치된 Python 3.10 이상을 쓴다. 없으면 uv 로 Python 3.14 를 이 폴더 안에만 받는다(관리자 권한 불필요).
#      두 시스템이 같은 가상 환경 .run\venv 를 쓴다.
#   3. 변환기: .run\venv 에 PyMuPDF 1.27.2.3(pdf 변환용, 시험한 버전)을 설치한다. 실패하면 pdf 만 빠지고 계속한다.
#      경매: 표준 라이브러리만 써서 설치할 것이 없다.
#   4. 지난 실행 상태를 지운다. 변환기는 data\, plugins\csv_conv.py 를 지우고 시연 자료(samples\)를 만든다.
#      경매는 data\, plugins\lowest_unique.py 를 지운다.
#   5. 빈 포트(변환기 8802~8830, 경매 8801 다음 8831~8850)를 골라 서버를 켜고 브라우저를 연다. 경매는 사용자 두 명용으로 탭을 두 개 연다.
#      끄려면 이 창에서 Ctrl+C. 두 시스템을 각자 다른 창에서 함께 켜 두어도 된다.
#
# 시험용 환경 변수: HW3_APP(docconv|auction), HW3_DIR(설치 폴더), HW3_ZIP(ZIP 경로나 주소), HW3_FORCE_UV=1, HW3_NO_BROWSER=1

& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    } catch {}

    $ZipUrl = 'https://github.com/Daejin8753/JBNU-SW_Architecture-HW3/archive/refs/heads/main.zip'
    $MinPy = [version]'3.10'
    $PyMuPdfVersion = '1.27.2.3'

    function Step($n, $msg) { Write-Host ''; Write-Host "[$n/5] $msg" -ForegroundColor Cyan }
    function Info($msg) { Write-Host "      $msg" }
    function Warn($msg) { Write-Host "      주의: $msg" -ForegroundColor Yellow }
    function Fail($msg) { Write-Host ''; Write-Host "중단: $msg" -ForegroundColor Red }

    function Get-File($src, $dest) {
        if ($src -match '^https?://') { Invoke-WebRequest -UseBasicParsing -Uri $src -OutFile $dest }
        else { Copy-Item -LiteralPath $src -Destination $dest }
    }

    # 외부 프로그램을 돌려 (종료 코드, 출력)을 돌려준다. stderr 는 버린다.
    function Invoke-Quiet($exe, [string[]]$argv) {
        $ErrorActionPreference = 'Continue'
        try {
            $out = & $exe @argv 2>$null
            return @{ Code = $LASTEXITCODE; Out = (($out | Out-String).Trim()) }
        } catch {
            return @{ Code = 1; Out = '' }
        }
    }

    function Get-PyVersion($exe, [string[]]$pre) {
        $r = Invoke-Quiet $exe ($pre + @('-c', "import sys;print('%d.%d' % sys.version_info[:2])"))
        if ($r.Code -eq 0 -and $r.Out -match '^\d+\.\d+$') { return [version]$r.Out }
        return $null
    }

    function Test-PortBusy([int]$port) {
        $c = New-Object Net.Sockets.TcpClient
        try {
            $ar = $c.BeginConnect('127.0.0.1', $port, $null, $null)
            if (-not $ar.AsyncWaitHandle.WaitOne(300)) { return $false }
            $c.EndConnect($ar)
            return $true
        } catch {
            return $false
        } finally {
            $c.Close()
        }
    }

    # 켤 시스템. bat 이 HW3_APP 를 정하고, 없으면 변환기다.
    $target = 'docconv'
    if ($env:HW3_APP) { $target = $env:HW3_APP.Trim().ToLowerInvariant() }
    if (@('docconv', 'auction') -notcontains $target) {
        Fail "HW3_APP 값 '$($env:HW3_APP)' 을(를) 모릅니다. docconv 또는 auction 이어야 합니다."
        return
    }
    $appName = "candidate-$target"
    if ($target -eq 'auction') {
        Write-Host '온라인 경매 (비교용 후보 A) 를 준비합니다.' -ForegroundColor Cyan
    } else {
        Write-Host '문서 → Markdown 변환기 (제출한 시스템) 를 준비합니다.' -ForegroundColor Cyan
    }

    # ---------------------------------------------------------------- 1. 폴더
    Step 1 '폴더 준비'
    $root = $env:HW3_DIR
    if (-not $root -and $PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "$appName\app.py"))) { $root = $PSScriptRoot }
    if (-not $root) {
        $desk = [Environment]::GetFolderPath('Desktop')
        if (-not $desk -or -not (Test-Path $desk)) { $desk = $HOME }
        $root = Join-Path $desk 'JBNU-HW3'
    }
    $root = [IO.Path]::GetFullPath($root)
    $app = Join-Path $root $appName

    if (Test-Path (Join-Path $app 'app.py')) {
        Info "이미 있는 폴더를 씁니다: $root"
    } else {
        if ((Test-Path $root) -and (Get-ChildItem -Force $root | Select-Object -First 1)) {
            Fail "$root 폴더가 비어 있지 않은데 $appName 이 없습니다. 폴더를 지우거나 옮긴 뒤 다시 실행하십시오."
            return
        }
        $src = $env:HW3_ZIP
        if (-not $src) { $src = $ZipUrl }
        Info "내려받는 중: $src"
        $tmp = Join-Path ([IO.Path]::GetTempPath()) ('hw3-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
        New-Item -ItemType Directory -Path $tmp | Out-Null
        try {
            $zip = Join-Path $tmp 'repo.zip'
            Get-File $src $zip
            Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $tmp 'x')
            $top = Join-Path $tmp 'x'
            $dirs = @(Get-ChildItem -LiteralPath $top -Directory)
            if (-not (Test-Path (Join-Path $top $appName)) -and $dirs.Count -eq 1) { $top = $dirs[0].FullName }
            if (-not (Test-Path (Join-Path $top "$appName\app.py"))) { throw "ZIP 안에 $appName\app.py 가 없습니다." }
            New-Item -ItemType Directory -Force -Path $root | Out-Null
            Get-ChildItem -LiteralPath $top -Force | Move-Item -Destination $root
        } catch {
            Fail "내려받기·압축 풀기에 실패했습니다: $($_.Exception.Message)"
            return
        } finally {
            Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
        }
        Info "받았습니다: $root"
    }

    # ---------------------------------------------------------------- 2. Python
    Step 2 'Python 준비'
    $run = Join-Path $root '.run'
    $venv = Join-Path $run 'venv'
    $vpy = Join-Path $venv 'Scripts\python.exe'
    $uv = Join-Path $run 'uv\uv.exe'

    $ok = (Test-Path $vpy) -and ((Get-PyVersion $vpy @()) -ge $MinPy)
    if ($ok) {
        Info "이미 만든 가상 환경을 씁니다 (Python $(Get-PyVersion $vpy @()))"
    } else {
        if (Test-Path $venv) { Remove-Item -LiteralPath $venv -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $run | Out-Null
        if (-not $env:HW3_FORCE_UV) {
            $cands = @()
            if (Get-Command py -ErrorAction SilentlyContinue) { $cands += , @('py', @('-3')) }
            if (Get-Command python -ErrorAction SilentlyContinue) { $cands += , @('python', @()) }
            foreach ($c in $cands) {
                $v = Get-PyVersion $c[0] $c[1]
                if (-not $v) { continue }
                if ($v -lt $MinPy) { Info "Python $v 은 너무 낮아 쓰지 않습니다 ($MinPy 이상 필요)"; continue }
                Info "설치된 Python $v 으로 가상 환경을 만듭니다"
                $r = Invoke-Quiet $c[0] ($c[1] + @('-m', 'venv', $venv))
                if ($r.Code -eq 0 -and (Test-Path $vpy)) { $ok = $true; break }
                Warn "가상 환경 만들기 실패 (종료 코드 $($r.Code))"
                Remove-Item -LiteralPath $venv -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        if (-not $ok) {
            Info '쓸 수 있는 Python 이 없어 uv 로 Python 3.14 를 이 폴더 안에 받습니다 (1~2분)'
            try {
                if (-not (Test-Path $uv)) {
                    $arch = 'x86_64'
                    if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { $arch = 'aarch64' }
                    $uvZip = Join-Path $run 'uv.zip'
                    Get-File "https://github.com/astral-sh/uv/releases/latest/download/uv-$arch-pc-windows-msvc.zip" $uvZip
                    Expand-Archive -LiteralPath $uvZip -DestinationPath (Join-Path $run 'uv-x') -Force
                    $found = Get-ChildItem -LiteralPath (Join-Path $run 'uv-x') -Recurse -Filter 'uv.exe' | Select-Object -First 1
                    New-Item -ItemType Directory -Force -Path (Split-Path $uv) | Out-Null
                    Move-Item -LiteralPath $found.FullName -Destination $uv -Force
                    Remove-Item -LiteralPath $uvZip, (Join-Path $run 'uv-x') -Recurse -Force -ErrorAction SilentlyContinue
                }
                $env:UV_PYTHON_INSTALL_DIR = Join-Path $run 'python'
                $env:UV_CACHE_DIR = Join-Path $run 'uv-cache'
                & $uv venv --quiet --python 3.14 --python-preference only-managed $venv
                $ok = ($LASTEXITCODE -eq 0) -and (Test-Path $vpy)
            } catch {
                $ok = $false
            }
            if (-not $ok) {
                Fail 'Python 을 준비하지 못했습니다. 인터넷 연결을 확인하거나 python.org 에서 Python 3.14 를 설치한 뒤 다시 실행하십시오.'
                return
            }
        }
        Info "가상 환경 준비 완료 (Python $(Get-PyVersion $vpy @()))"
    }

    # ---------------------------------------------------------------- 3. 추가 라이브러리
    if ($target -eq 'auction') {
        Step 3 '추가 라이브러리 확인'
        Info '경매는 Python 표준 라이브러리만 써서 설치할 것이 없습니다'
    } else {
        Step 3 'PyMuPDF 확인 (pdf 변환용)'
        if ((Invoke-Quiet $vpy @('-c', 'import fitz')).Code -eq 0) {
            Info '이미 설치되어 있습니다'
        } else {
            Info '설치하는 중...'
            $hasPip = (Invoke-Quiet $vpy @('-m', 'pip', '--version')).Code -eq 0
            # 시험을 마친 버전을 먼저 받고, 안 되면 최신판을 받는다.
            foreach ($spec in @("pymupdf==$PyMuPdfVersion", 'pymupdf')) {
                if ($hasPip) { & $vpy -m pip install --quiet --disable-pip-version-check $spec }
                elseif (Test-Path $uv) { & $uv pip install --quiet --python $vpy $spec }
                if ((Invoke-Quiet $vpy @('-c', 'import fitz')).Code -eq 0) { break }
            }
            $r = Invoke-Quiet $vpy @('-c', 'import pymupdf;print(pymupdf.VersionBind)')
            if ($r.Code -eq 0) { Info "설치했습니다 (PyMuPDF $($r.Out))" }
            else { Warn 'PyMuPDF 를 설치하지 못했습니다. pdf 시연만 빠지고 나머지는 됩니다.' }
        }
    }

    # ---------------------------------------------------------------- 4. 시연 자료와 초기 상태
    if ($target -eq 'auction') {
        Step 4 '지난 실행 상태 지우기'
        $stale = @((Join-Path $app 'data'), (Join-Path $app 'plugins\lowest_unique.py'))
    } else {
        Step 4 '시연 자료 만들기, 지난 실행 상태 지우기'
        $stale = @((Join-Path $app 'data'), (Join-Path $app 'plugins\csv_conv.py'))
    }
    foreach ($p in $stale) {
        if (-not (Test-Path $p)) { continue }
        try { Remove-Item -LiteralPath $p -Recurse -Force }
        catch {
            Fail "$p 을(를) 지우지 못했습니다. 이 폴더로 켜 둔 서버 창이 있으면 닫고(Ctrl+C) 다시 실행하십시오."
            return
        }
    }
    if ($target -eq 'auction') {
        Info '경매 기록(data\)과 시연 중 복사한 lowest_unique.py 를 지웠습니다. 플러그인은 기본 상태로 시작합니다.'
    } else {
        & $vpy -B (Join-Path $app 'tools\make_samples.py') | Out-Null
        if ($LASTEXITCODE -ne 0) { Fail '시연 자료를 만들지 못했습니다.'; return }
        Info ("samples\: " + ((Get-ChildItem -LiteralPath (Join-Path $app 'samples') -File | ForEach-Object Name) -join ', '))
    }

    # ---------------------------------------------------------------- 5. 실행
    Step 5 '서버 실행'
    if ($target -eq 'auction') {
        $ports = @(8801) + (8831..8850); $range = '8801, 8831~8850'; $tabs = 2
    } else {
        $ports = 8802..8830; $range = '8802~8830'; $tabs = 1
    }
    $port = 0
    foreach ($p in $ports) { if (-not (Test-PortBusy $p)) { $port = $p; break } }
    if (-not $port) { Fail "$range 포트가 모두 쓰이고 있습니다."; return }
    if ($port -ne $ports[0]) { Warn "$($ports[0]) 포트에 이미 다른 서버가 있어 $port 포트를 씁니다. 예전에 켠 서버 창이 있으면 닫아 두십시오." }
    $url = "http://127.0.0.1:$port"

    Write-Host ''
    Write-Host "  브라우저 : $url" -ForegroundColor Green
    Write-Host "  코드 폴더: $app"
    if ($target -eq 'auction') {
        Write-Host '  사용자   : 탭을 두 개 엽니다. 탭마다 위쪽 이름 칸에 갑, 을처럼 다른 이름을 넣습니다.'
        Write-Host "  시연 6 의 새 경매 방식 복사: 아래 파일을 더블클릭합니다."
        Write-Host "    $root\demo-add-auction-type.bat"
    } else {
        Write-Host "  시연 5 의 csv 플러그인 복사: 아래 파일을 더블클릭합니다."
        Write-Host "    $root\demo-add-csv.bat"
    }
    Write-Host '  끄기     : 이 창에서 Ctrl+C'
    Write-Host ''

    $job = $null
    if (-not $env:HW3_NO_BROWSER) {
        $job = Start-Job -ArgumentList $url, $port, $tabs -ScriptBlock {
            param($u, $p, $n)
            for ($i = 0; $i -lt 80; $i++) {
                $up = $false
                try { $c = New-Object Net.Sockets.TcpClient('127.0.0.1', $p); $c.Close(); $up = $true }
                catch { Start-Sleep -Milliseconds 250 }
                if ($up) {
                    for ($k = 0; $k -lt $n; $k++) { if ($k) { Start-Sleep -Milliseconds 1500 }; Start-Process $u }
                    return
                }
            }
        }
    }
    Push-Location -LiteralPath $app
    try {
        & $vpy -B (Join-Path $app 'app.py') --port $port
    } finally {
        Pop-Location
        if ($job) { Remove-Job -Job $job -Force -ErrorAction SilentlyContinue }
    }
}
