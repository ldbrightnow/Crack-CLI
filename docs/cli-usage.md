# Crack CLI 사용법

Crack CLI는 Codex 작업 흐름을 작은 명령들로 실행하는 orchestrator다. 사용자 요청을 Plan으로 라우팅하고, Plan의 커밋 단위를 순서대로 구현하며, 완료된 브랜치를 로컬에 남기거나 원격 PR과 merge까지 이어갈 수 있다.

상태의 source of truth는 저장소 안의 `.crack/` Markdown 파일이다.

```text
.crack/
  inbox.md
  pr-lock.md
  plans/
    <plan-name>/
      plan.md
      queue.md
      log.md
```

## 준비

로컬에서 CLI를 빌드한다.

```bash
npm install
npm run build
```

이 문서의 예시는 `crack` 명령을 기준으로 한다. 전역 링크를 만들지 않았다면 `node dist/src/cli.js`로 바꿔 실행할 수 있다.

```bash
npm link
crack --help
```

`submit`, `route`, `run-next`, `run-all`, conflict resolution이 필요한 `merge`는 내부에서 `codex exec`를 실행한다. 원격 PR 관련 명령은 `gh` CLI와 GitHub 인증이 필요하다.

## Coding Agent Skill

이 저장소에는 Crack CLI를 코딩 에이전트가 바로 사용할 수 있도록 Skill 형태로도 제공한다.

```text
skills/crack-cli/
  SKILL.md
  agents/openai.yaml
```

Codex 계열 에이전트에 설치하려면 Skill 디렉터리를 `$CODEX_HOME/skills` 아래로 복사한다. `CODEX_HOME`을 따로 쓰지 않는 환경에서는 보통 `~/.codex/skills`를 사용한다.

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R skills/crack-cli "${CODEX_HOME:-$HOME/.codex}/skills/crack-cli"
```

설치 후에는 `$crack-cli`로 명시 호출하거나, Crack CLI workflow 관련 요청에서 에이전트가 자동으로 이 Skill을 사용할 수 있다.

## 빠른 흐름

```bash
crack init
crack submit "사용자 요청"
crack dashboard
crack run-all --plan .crack/plans/<plan>/plan.md
```

기본 흐름에서는 모든 커밋 단위가 완료되어도 원격 PR을 열지 않고 로컬 브랜치 완료 상태로 멈춘다. 원격 draft PR까지 열려면 remote mode를 명시한다.

```bash
crack run-all --plan .crack/plans/<plan>/plan.md --remote
```

완료된 Plan을 로컬에서 바로 merge하려면 다음처럼 실행한다.

```bash
crack merge --plan .crack/plans/<plan>/plan.md
```

## 공통 옵션

모든 명령은 `--root <path>`를 받을 수 있다. 생략하면 현재 디렉터리에서 위로 올라가며 가장 가까운 `.git` 디렉터리를 저장소 루트로 사용한다.

```bash
crack dashboard --root /path/to/repo
```

## 명령

### `crack init`

`.crack/` 상태 디렉터리를 초기화한다. 기존 `inbox.md`가 있으면 덮어쓰지 않는다.

```bash
crack init
```

성공하면 `initialized <repo>/.crack`을 출력한다.

### `crack submit <prompt>`

사용자 요청을 workflow에 넣는다. `route`는 같은 동작을 하는 alias다.

```bash
crack submit "Add a dashboard command"
crack route "Fix the failing merge test"
```

동작은 현재 상태에 따라 달라진다.

- `.crack/pr-lock.md`가 있으면 새 Plan을 만들지 않고 `.crack/inbox.md`에 요청을 추가한다.
- `--plan <path>`를 주면 해당 Plan의 `queue.md`에 요청을 추가한다.
- active plan이 있으면 Router agent가 기존 Plan에 붙일지 새 Plan을 만들지 판단한다.
- 새 Plan을 만들 때는 branch를 준비하고 Planner agent가 `plan.md`를 작성한다.

사용 가능한 옵션:

```bash
crack submit "요청" --plan .crack/plans/demo/plan.md
crack submit "요청" --branch codex/demo --title "Demo" --reason "Manual route"
```

`--branch`와 `--title`은 새 Plan 생성 시 사용한다. `--reason`은 `queue.md`, `inbox.md`, `log.md`에 남길 라우팅 이유를 바꾸고 싶을 때 사용한다.

### `crack dashboard`

현재 `.crack/` 상태와 git 변경 요약을 읽기 전용으로 보여준다.

```bash
crack dashboard
crack dashboard --watch
crack dashboard --watch --interval 5
```

표시 내용:

- PR lock 여부
- inbox 요청 수
- dirty file 수
- active plan 목록
- 각 plan의 commit unit 진행률
- 다음에 실행할 commit unit
- 추천 `run-all` 명령
- 최근 log

`--interval`은 `--watch`와 함께만 사용할 수 있다.

### `crack run-next`

선택한 Plan의 다음 미완료 commit unit 하나만 구현한다.

```bash
crack run-next --plan .crack/plans/demo/plan.md
```

`--plan`을 생략하면 active plan이 하나일 때만 자동 선택한다. 여러 Plan이 있으면 명시해야 한다.

실행 전 working tree가 깨끗해야 한다. dirty file이 있으면 중단한다.

동작 순서:

1. `plan.md`의 `### Commit N:` 항목과 `log.md`의 완료 기록을 비교해 다음 unit을 고른다.
2. Codex implementer session을 시작해 해당 unit만 구현한다.
3. 같은 session에 검토 prompt를 보낸다.
4. 구현 결과가 ready이면 Crack CLI가 변경 파일을 stage하고 git commit을 만든다.
5. 완료 기록을 `log.md`에 append한다.
6. Plan이 완료 상태가 되었으면 PR opening 단계도 확인한다.

기본 branch mode는 `local`이다. 따라서 마지막 unit까지 끝나도 원격 PR을 열지 않고 로컬 브랜치 완료 상태로 기록한다. 원격 draft PR까지 열려면 다음처럼 실행한다.

```bash
crack run-next --plan .crack/plans/demo/plan.md --remote
```

### `crack run-all`

선택한 Plan의 남은 commit unit을 `run-next` 규칙으로 끝까지 반복한다.

```bash
crack run-all --plan .crack/plans/demo/plan.md
crack run-all --plan .crack/plans/demo/plan.md --remote
```

commit unit 하나가 `needs_work`를 반환하면 즉시 멈춘다. 모든 unit이 끝나면 branch mode에 따라 로컬 완료 상태로 두거나 draft PR을 연다.

`--branch-mode local|remote`와 `--remote`를 사용할 수 있다. `--remote`는 `--branch-mode remote`와 같다.

### `crack open-pr`

완료된 Plan에 대해 PR opening 단계만 실행한다.

```bash
crack open-pr --plan .crack/plans/demo/plan.md
```

`open-pr`의 기본 branch mode는 `remote`다. Plan의 모든 commit unit이 완료되어 있어야 하며, 성공하면 현재 branch를 push하고 GitHub draft PR을 만든 뒤 `.crack/pr-lock.md`를 생성한다.

로컬 완료 상태만 다시 기록하려면 명시적으로 local mode를 쓴다.

```bash
crack open-pr --plan .crack/plans/demo/plan.md --branch-mode local
```

### `crack merge`

완료된 Plan의 branch를 target branch에 merge한다.

```bash
crack merge --plan .crack/plans/demo/plan.md
crack merge --plan .crack/plans/demo/plan.md --target release
```

기본 target은 `main`이고, 기본 branch mode는 `local`이다. local mode에서는 working tree가 깨끗한지 확인하고 target branch로 전환한 뒤 Plan의 source branch를 merge한다.

원격 PR 경유로 merge하려면 remote mode를 사용한다.

```bash
crack merge --plan .crack/plans/demo/plan.md --remote
crack merge --plan .crack/plans/demo/plan.md --branch-mode remote --target release
```

remote mode는 source branch를 push하고, 기존 PR이 있으면 재사용하거나 새 ready PR을 만든 뒤 `gh pr merge --merge`를 실행한다. merge 가능하지 않은 상태가 target branch 변경 때문이면 source branch를 target에서 업데이트한 뒤 다시 시도한다.

local 또는 remote merge 중 conflict가 생기면 Merge agent가 현재 merge conflict만 해결하도록 호출된다. 해결되지 않으면 `merge_needs_work`로 멈추고 `log.md`에 이유를 남긴다.

### `crack pr-check`

`.crack/pr-lock.md`가 가리키는 PR 상태를 확인한다.

```bash
crack pr-check
```

- lock이 없으면 `pr_check: no active PR lock`을 출력한다.
- PR이 아직 open 또는 closed 상태면 lock을 유지한다.
- PR이 merged 상태면 lock을 삭제하고 `drain`을 실행해 `inbox.md` 요청을 다시 라우팅한다.

### `crack drain`

`.crack/inbox.md`에 쌓인 요청을 순서대로 다시 Router에 넣는다.

```bash
crack drain
```

PR lock이 남아 있으면 drain하지 않고 중단한다. drain 중 새 lock이 생기면 남은 요청은 inbox에 보존된다.

### `crack set-pr-lock`

PR review lock을 수동으로 만든다.

```bash
crack set-pr-lock \
  --branch codex/demo \
  --pr-url https://github.com/example/repo/pull/123 \
  --reason "Draft PR is under review" \
  --status reviewing
```

lock이 있는 동안 `submit`과 `route`는 새 Plan을 만들지 않고 요청을 `inbox.md`에 쌓는다.

### `crack clear-pr-lock`

PR review lock을 수동으로 제거한다.

```bash
crack clear-pr-lock
```

lock 제거 후 대기 중인 요청을 처리하려면 `crack drain`을 실행한다.

## 출력과 종료 코드

CLI는 한 줄 또는 여러 줄의 상태 메시지를 출력한다.

```text
create_new_plan: .crack/plans/<name>/plan.md
route_to_existing_plan: .crack/plans/<name>/queue.md
pause_for_pr_review: .crack/inbox.md
committed unit 1: <hash> <message>
needs_work unit 2: <reason>
local_branch: codex/demo; Plan is complete on a local branch; remote PR was not opened.
opened_pr: https://github.com/example/repo/pull/123 (Demo)
merge_needs_work: <reason>
```

대부분의 성공 경로는 종료 코드 `0`을 반환한다. `needs_work`, 잘못된 옵션, missing required flag, dirty working tree, external CLI 실패는 종료 코드 `1`을 반환한다.

## 운영 팁

- `run-next`, `run-all`, `merge` 전에는 `git status --short`로 working tree가 깨끗한지 확인한다.
- 여러 active plan이 있으면 `--plan`을 명시한다.
- 진행 상황을 보면서 실행하려면 다른 터미널에서 `crack dashboard --watch`를 켠다.
- 원격 PR이 필요한 경우에만 `--remote`를 사용한다. 기본값은 로컬 완료 상태를 유지하는 쪽이다.
- PR review 중 새 요청을 잃지 않으려면 lock을 유지하고, merge 후 `pr-check` 또는 `drain`으로 inbox를 비운다.
