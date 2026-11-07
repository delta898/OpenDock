# OpenDock Blog Seeds

이 문서는 OpenDock를 함께 개발하며 얻은 경험을 BlogGenius가 구체적인
글로 발전시킬 수 있도록 축적하는 글감 백로그다. 일반적인 기술 설명보다
OpenDock에서 실제로 겪은 문제, 판단 근거, 실패와 검증 결과를 우선한다.

상태는 `seed`, `ready`, `drafted`, `published` 중 하나를 사용한다. 현재
항목은 모두 글감 수집 단계인 `seed`이며, 사용자의 요청 없이 상태를
올리거나 게시 작업을 수행하지 않는다.

## OD-001. OpenDock란 무엇인가: 한 서버의 운영 지식을 저장소로 만드는 방법

- 상태: `seed`
- 관련 이력: `d56e8ec`, `7783845`, `5ce911b`, `c7d39e7`, `209d760`
- 주제: `OpenDock란 무엇인가—git clone과 make launch 사이에 숨은 운영 철학`
- 독자 질문: Docker Compose 파일 모음과 OpenDock의 차이는 무엇이며, 어떤
  사람과 환경에서 가치가 있는가?
- 참고할 사항:
  - OpenDock는 WordPress, Nextcloud, Immich, Jellyfin, Mastodon,
    Mattermost, n8n, Supabase 등을 단순히 나열한 저장소가 아니다. 각
    프로젝트마다 달랐던 설정, Secret, 의존 인프라, 상태 확인, Gateway,
    공개 경로를 저장소 루트의 공통 명령으로 운영하는 것이 핵심이다.
  - 초기에 개별 Compose workspace와 Gateway 기본값으로 시작했지만,
    서비스가 늘면서 `make setup`, `make launch <target>`, 자동 Secret 생성,
    설정 검증, post-launch hook으로 운영 지식이 점차 코드가 되었다.
  - zero-config는 “설정이 없다”는 뜻이 아니다. 도메인·SMTP처럼 사람의
    의도가 필요한 값은 질문하고, 비밀번호·JWT·API key처럼 기계가 만들
    수 있는 값은 안전하게 생성하며, 서비스 시작 순서와 검증은 자동화가
    책임진다는 구분이다.
  - 대표 흐름은 `make setup` 후 `make launch <service>`다. 단일 서비스를
    요청해도 공유 Docker network와 infra를 준비하고, 서비스별 후처리,
    Caddy 갱신, Cloudflare route 처리를 이어간다.
  - 적합한 범위는 한 대의 Linux 서버에서 여러 오픈소스 서비스를
    이해 가능하고 재현 가능하게 운영하려는 개인, 홈랩, 소규모 팀이다.
    다중 노드 고가용성·자동 확장·관리형 백업을 제공하는 Kubernetes나
    상용 PaaS의 대체품이라고 과장하지 않는다.
- 보존할 교훈:
  - 편리함보다 재현성, 데이터 통제권, 운영 규칙의 가시성, 새 서버에서의
    복구 가능성이 핵심 가치다.
  - 좋은 자동화는 복잡성을 감추기만 하지 않고 실패한 계층을 드러내야 한다.
- 검증 상태: 여러 단일 서비스와 Supabase 기본 스택의 `make launch` 흐름을
  실제 환경에서 사용했다. 모든 서비스를 동시에 새 서버에 설치하는 시나리오는
  별도 검증으로 표현해야 한다.

## OD-002. Supabase unhealthy 연쇄 장애를 아래 계층부터 푼 과정

- 상태: `seed`
- 관련 이력: `c2b2a7f` 및 Supabase 도입 과정의 실환경 로그
- 주제: `dependency failed는 원인이 아니었다—Self-hosted Supabase 연쇄 장애 추적기`
- 독자 질문: Docker Compose가 한 컨테이너를 unhealthy라고만 말할 때 실제
  원인을 어떻게 좁혀야 하는가?
- 참고할 사항:
  - 첫 장애는 `supabase-db is unhealthy`였고 실제 로그는 PostgreSQL 15가
    만든 data directory를 PostgreSQL 17.6이 열 수 없다는 내용이었다.
    기존 볼륨을 유지한 채 이미지 major version만 올리는 것이 왜 실패하는지
    보여주는 명확한 사례다. 폐기 가능한 데이터는 삭제 대신 backup 경로로
    이동해 복구 가능성을 남겼다.
  - DB가 정상화되자 PostgREST가 `graphql_public` schema 부재로 실패했다.
    다음에는 Realtime이 `_realtime` schema의 search path 문제로, bootstrap은
    `supabase_functions_admin` role 부재로, 마지막에는 Storage가 unhealthy로
    드러났다. 상위 서비스가 회복될 때마다 다음 실제 의존성 문제가 보였다.
  - `docker inspect`의 Health log가 비어 있어도 컨테이너 로그는 결정적인
    단서를 제공했다. 많은 로그 전체가 아니라 실패 컨테이너별 마지막 수십
    줄을 받아 첫 SQLSTATE와 최초 오류를 찾는 방식이 효과적이었다.
  - 최종 설계는 DB 이미지 초기화에만 기대지 않고, 기존 compatible DB에도
    필요한 schema·role·ownership을 복구하는 idempotent
    `supabase-db-bootstrap`을 둔다. 서비스들은 bootstrap 완료를 dependency로
    기다린다.
- 보존할 교훈:
  - Compose의 `dependency failed`와 `unhealthy`는 증상이다. 가장 아래의
    stateful dependency부터 해결하고, 한 번에 여러 추측을 적용하지 않는다.
  - major DB upgrade와 애플리케이션 schema bootstrap은 서로 다른 문제다.
  - “깨끗한 첫 설치”뿐 아니라 중간 상태의 기존 볼륨에서도 반복 실행 가능한
    초기화가 zero-config 운영에 필요하다.
- 검증 상태: DB, REST, Realtime, Auth, Studio를 차례로 회복했고 사용자가
  최종적으로 로그인하여 Dashboard가 뜨는 것을 실환경에서 확인했다.

## OD-003. 12개 구성요소를 하나의 zero-config Supabase 서비스로 묶기

- 상태: `seed`
- 관련 이력: `c2b2a7f`
- 주제: `make launch supabase 하나로 Self-hosted Supabase를 구성하려면`
- 독자 질문: 공식 Compose 예제를 가져오는 것과 운영 가능한 서비스로
  통합하는 것 사이에는 어떤 작업이 필요한가?
- 참고할 사항:
  - Supabase는 단일 컨테이너가 아니라 전용 PostgreSQL, Auth, PostgREST,
    Realtime, Storage, imgproxy, postgres-meta, Studio, Edge Runtime, Kong,
    Inbucket, DB bootstrap이 함께 움직이는 multi-container 서비스다.
  - 시작 순서는 단순 `depends_on` 존재 여부가 아니라 `service_healthy`와
    `service_completed_successfully` 조건으로 표현했다. 느린 디스크의 첫
    migration을 견디도록 DB healthcheck의 start period와 retry도 넉넉히 뒀다.
  - OpenDock의 post-launch smoke test는 컨테이너 실행 여부만 보지 않는다.
    필수 schema·role, Auth, REST, GraphQL, Storage, Realtime, Studio와 포함된
    Edge Function을 실제 호출해 partial success를 성공으로 보고하지 않는다.
  - Studio 관리 화면은 Basic Auth로 보호하지만 `/auth/v1`, `/rest/v1`,
    `/graphql/v1`, `/realtime/v1`, `/storage/v1`, `/functions/v1`은 애플리케이션
    API key와 사용자 JWT/RLS가 담당한다. 관리 화면 인증과 API 인증을 같은
    보호막으로 처리하지 않은 것이 중요한 경계다.
  - `make launch supabase`가 infra network 준비, Secret 생성, 구성 검사,
    health order 기동, smoke test, Gateway reload, route publish를 잇는다.
- 보존할 교훈:
  - multi-container 제품의 zero-config는 Compose 파일 길이가 아니라 초기
    상태, dependency gate, 복구 가능한 bootstrap, end-to-end 검증의 문제다.
  - healthcheck는 “프로세스가 살아 있음”보다 실제 downstream 계약을 얼마나
    확인하는지가 중요하다.
- 검증 상태: 기본 Supabase 스택의 healthy 상태와 Studio 로그인을 사용자가
  실환경에서 확인했다. 신형 publishable key 경로는 OD-005의 검증 상태를
  별도로 따른다.

## OD-004. Edge Function Secret을 Studio 소스와 분리한 이유

- 상태: `seed`
- 관련 이력: `72c3cc5`
- 주제: `env 파일을 Dashboard에 마운트하면 Secret 관리가 될까?`
- 독자 질문: Self-hosted Supabase Edge Function의 사용자 Secret을 어디에
  두어야 코드 편집 편의와 보안을 함께 지킬 수 있는가?
- 참고할 사항:
  - 처음 검토한 안은 `config/functions/.env.functions`였다. 그러나 현재
    `config/functions/`는 Edge Runtime뿐 아니라 Studio의 함수 관리 폴더에도
    mount된다. env 파일을 그 안에 둔다고 Dashboard의 Secret CRUD가 되는
    것이 아니라, Studio가 읽을 수 있는 일반 소스 파일이 될 가능성이 생긴다.
  - 최종 구조는 함수 코드는 `config/functions/`, 사용자 Secret은 형제 파일인
    `services/supabase/functions.env`로 분리했다. Compose의 optional `env_file`은
    이 파일을 Edge Runtime에만 주입한다.
  - `functions.env.example`은 Git에 포함하고 실제 `functions.env`는 첫
    `make launch supabase`에서 자동 생성한다. 파일 권한은 `0600`, Git과
    OpenDock rsync에서는 제외한다. Secret이 비어 있어도 기본 Supabase 기동을
    막지 않아 zero-config를 유지한다.
  - `make action supabase functions-secrets`는 값은 출력하지 않고 설정된
    변수명, 파일 권한, 수정·적용 명령만 안내한다. 변경 적용에는 컨테이너
    recreate가 필요한 `make up supabase`를 사용한다.
  - 현재 단일 Edge Runtime dispatcher가 모든 container environment를 worker에
    전달하므로 모든 함수가 같은 사용자 Secret 집합을 볼 수 있다. 함수별
    격리가 필요하면 runtime 분리가 별도 설계 과제다.
- 보존할 교훈:
  - 파일이 UI 컨테이너에 보인다는 사실과 Secret 관리 기능은 전혀 다르다.
  - code plane과 secret/config plane을 디렉터리 수준에서 분리하면 미래 UI
    변경에도 노출 범위를 줄일 수 있다.
- 검증 상태: 자동 생성, `0600`, Git ignore, sync 제외, Compose 환경변수
  주입과 action의 값 비노출을 로컬에서 검증했다.

## OD-005. anon JWT에서 sb_publishable로 옮긴 Self-hosted API key 설계

- 상태: `seed`
- 관련 이력: `ab4e3f4`
- 주제: `sb_publishable 문자열 하나를 추가하는 것으로는 부족했다`
- 독자 질문: Self-hosted Supabase에서 신형 opaque API key를 기존 서비스와
  호환되게 도입하려면 무엇이 함께 바뀌어야 하는가?
- 참고할 사항:
  - OpenDock 초기 구성에는 `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
    `SUPABASE_JWT_SECRET`만 있었다. publishable key가 필요하다는 요구에서
    시작했지만, `sb_publishable_...`를 임의 생성해 env에 넣는 것만으로는
    downstream 서비스가 이를 JWT로 검증할 수 없다.
  - 공식 self-host 구조에 맞춰 P-256 key pair, private signing JWK 목록,
    public JWKS, 내부 `anon`/`service_role` ES256 role JWT, opaque
    `sb_publishable`/`sb_secret`을 하나의 일관된 bundle로 자동 생성했다.
  - Kong은 외부 opaque key를 key-auth로 식별한 뒤 내부 ES256 role JWT로
    번역한다. 실제 사용자 session JWT가 Authorization에 있으면 이를 보존하고,
    Realtime WebSocket의 query-string `apikey`도 별도 표현식으로 번역한다.
  - Auth는 private signing keys로 새 session JWT를 발급하고 PostgREST,
    Realtime, Storage, Functions는 public JWKS로 검증한다. 기존 HS256 secret을
    JWKS에 함께 포함해 legacy anon/service-role key도 단계적으로 유지한다.
  - Edge Function dispatcher는 HS256·ES256 사용자 JWT뿐 아니라 configured
    opaque key를 구분한다. Browser/CLI에 보여줄 값은
    `make action supabase api-keys`로 publishable key만 출력하고 elevated key와
    signing material은 숨긴다.
  - `JWT_SECRET`, `sb_secret`, legacy `service_role`은 publishable field에 넣으면
    안 된다는 운영상의 구분을 명시해야 한다.
- 보존할 교훈:
  - API key는 애플리케이션을 식별하고 user JWT는 사용자를 식별한다. opaque
    key 도입은 문자열 형식 변경이 아니라 Gateway translation과 signing key
    distribution의 변경이다.
  - 호환 마이그레이션에서는 새 키를 기본으로 안내하되 legacy key를 내부에서
    즉시 제거하지 않는 단계적 전환이 안전하다.
- 검증 상태: key bundle 생성, ES256 서명, public/private JWKS 일관성,
  잘못된 bundle 탐지, Compose rendering을 로컬에서 검증했다. 새 키로 모든
  컨테이너를 재기동한 end-to-end 실환경 호출은 당시 승인 취소로 수행하지
  못했으므로 글에서 완료된 운영 검증처럼 표현하지 않는다.

## OD-006. 설정을 사용자 의도와 기계 Secret으로 분류한 smart-config

- 상태: `seed`
- 관련 이력: `6dd054e`, `11290b8`, `209d760`, `e9ad00b`
- 주제: `설정을 전부 묻지도, 전부 자동 생성하지도 않는 CLI 설계`
- 독자 질문: 서비스가 늘어날 때 초보자에게는 간단하면서 자동화에도 안전한
  설정 UX를 어떻게 만들 수 있는가?
- 참고할 사항:
  - 처음에는 `common.env.example` 복사와 수동 편집, 별도 Secret 생성으로
    시작했다. 서비스가 늘자 어떤 값은 반드시 사용자가 결정해야 하고 어떤
    값은 보여주지 않고 생성해야 하며 어떤 값은 기본값으로 충분한지가
    뒤섞였다.
  - `required-user`, `generated-secret`, `initial-credential`,
    `defaulted-choice`라는 분류를 만들었다. `STACK_DOMAIN`, 외부 SMTP와
    Cloudflare credential은 자동 생성하지 않는다. DB password, JWT와 app
    secret은 생성한다. 첫 로그인용 credential은 생성하되 사용자가 찾을 수
    있게 안내한다. subdomain 같은 값은 안전한 기본값을 제공한다.
  - `make setup [target]`은 대화형으로 사용자의 의도를 받고 기존 값에서
    Enter를 누르면 유지한다. `make secrets [target]`과 `make launch`는
    비대화형이며 누락된 generated secret만 채운다. launch가 질문을 시작하지
    않게 해 원격 자동화와 재실행 가능성을 보존했다.
  - 기존 실값은 덮어쓰지 않고 placeholder나 빈 값만 교체하며, 수정 전
    `common.env`를 timestamp backup한다. Supabase JWT secret처럼 서로 연동된
    값은 일부만 갱신하지 않고 bundle 단위로 다시 만든다.
  - `make check-config`는 읽기 전용이다. 시작 또는 Compose rendering 명령은
    같은 검사를 재사용하되 오류 시 사용자가 실행할 다음 명령을 알려준다.
- 보존할 교훈:
  - zero-config의 핵심은 질문 수를 0으로 만드는 것이 아니라 값의 소유자를
    정확히 나누는 것이다.
  - interactive setup과 non-interactive launch의 경계를 섞으면 자동화가
    예측 불가능해진다.
- 검증 상태: setup, Secret 보존·생성, backup과 check-config 흐름이 저장소의
  공통 운영 경로로 사용되고 있다.

## OD-007. Cloudflare Tunnel과 Caddy 사이에서 HTTPS 책임을 나눈 경험

- 상태: `seed`
- 관련 이력: `7783845`, `cabf30a`, `df1b323`
- 주제: `브라우저는 HTTPS인데 WordPress는 HTTP로 아는 이유`
- 독자 질문: Cloudflare Tunnel 뒤의 Caddy와 WordPress에서 redirect loop와
  HTTPS 오인식을 어떻게 피할 수 있는가?
- 참고할 사항:
  - OpenDock의 기본 공개 경로는 Browser → Cloudflare HTTPS → Tunnel →
    `http://localhost:80` Caddy → container다. 공개 구간이 HTTPS여도 origin
    요청은 HTTP일 수 있어 각 계층의 책임을 명시해야 한다.
  - Caddy의 origin-side 자동 HTTP→HTTPS redirect를 그대로 두면 Tunnel이
    HTTP origin으로 재접속하면서 redirect loop가 생길 수 있다. 기본 구성은
    `auto_https disable_redirects`로 origin redirect를 끄고 공개 redirect는
    Cloudflare가 담당한다.
  - WordPress는 내부 Apache가 HTTP 요청을 받기 때문에 HTTPS-only 기능과 URL
    생성이 잘못될 수 있었다. Caddy가 `X-Forwarded-Proto` 등을 전달하고,
    WordPress container 설정은 이를 읽어 `$_SERVER['HTTPS'] = 'on'`으로
    해석하도록 수정했다. 이로써 Application Password 같은 기능도 정상적인
    HTTPS 환경으로 인식한다.
  - 직접 port forwarding으로 Caddy를 public edge로 쓰는 고급 구성에서는
    반대로 redirect 비활성화를 제거하고 80/443을 전달해야 한다. 하나의
    설정이 모든 노출 방식에 맞는다고 설명하면 안 된다.
  - Cloudflare publish 자동화는 저장소의 route convention을 발견해 Tunnel
    public hostname과 DNS를 갱신하며, credential 파일이 없으면 실제 변경 대신
    게시할 route만 출력한다.
- 보존할 교훈:
  - TLS 종료 지점과 redirect 책임자를 먼저 그리지 않으면 proxy header 한두
    개를 고치는 방식으로는 문제를 반복하게 된다.
  - 애플리케이션이 인식하는 scheme과 사용자가 보는 scheme은 다를 수 있다.
- 검증 상태: WordPress proxy HTTPS 인식 수정과 Cloudflare/Caddy route 흐름은
  구현·문서화되었다. 직접 Caddy 공개 방식은 기본 지원 경로가 아니므로 별도
  운영 선택지로 표현한다.

## OD-008. 서비스별 명령을 `service` namespace로 확장하는 CLI 설계

- 상태: `seed`
- 관련 이력: `d963f76`, `63437c8`, `d5e6996`, `ca6daef`
- 주제: `service discovery, command, group, hook으로 홈서버 CLI 확장하기`
- 독자 질문: 서로 다른 서비스의 편의 기능을 공통 CLI에 추가하면서 어떻게
  거대한 조건문과 top-level 명령 증가를 피할 수 있는가?
- 참고할 사항:
  - `services/*/compose.yml`을 runtime에 발견하므로 새 서비스 추가에 Makefile
    목록 수정이 필요 없다. `services`, `all`, 단일 service라는 공통 target
    모델 위에 `media`, `communication`, `backend` 같은 목적별 group을
    `services/groups.conf`의 데이터로 추가했다.
  - WordPress multisite 같은 수동·파괴 가능 작업을 top-level 명령으로 늘리는
    대신 처음에는 `action <service> <action>` dispatcher로 모았다. Hermes의
    `setup hermes`와 `action hermes setup`이 헷갈린다는 피드백을 계기로
    사용자 관점의 namespace인 `service <service> <command>`로 바꾸고 내부
    디렉터리도 `services/<service>/commands/`로 통일했다.
  - 하위호환은 요구하지 않아 `action`, `services` top-level 별칭,
    `wp-multisite` shortcut은 제거한다. 서비스 목록은 `list services`, 전체 앱
    기동은 `up services`로 동사를 구분한다.
  - 자동 기동 뒤에만 필요한 Mastodon owner 생성이나 Supabase smoke test는
    `opendock-post-launch.py` hook으로 서비스에 귀속했다. 공통 launch는 hook의
    존재만 확인하며 서비스 세부 지식을 갖지 않는다.
  - 기능이 늘며 `make help`가 명령 이름 나열만으로는 부족해졌다. `launch`와
    `up`, `restart`, `services/all/group`, service command의 차이를 사용 시점
    중심으로 재구성했다. 읽기 전용 `make ps`, `make config`는 target 생략 시 `all`로
    동작하게 해 단순 누락을 Make error로 만들지 않았다.
  - `service <service>`만 입력하면 등록된 service commands를 발견하도록 한다.
- 보존할 교훈:
  - 공통 workflow는 mechanism을, service directory는 policy와 특수 동작을
    소유하게 하면 서비스 수가 늘어도 중심부가 안정적이다.
  - CLI help도 기능이며 실제 기본값과 오류 동작까지 맞아야 한다.
- 검증 상태: macOS Python 3.15.2에서 CLI/unit test 35개가 통과했다.
  `route`, `route add`, `setup`, service 목록과 service action의 단계별 help를
  실행해 확인했다. 특히 `service hermes onboard --help`가 onboarding 스크립트를
  실행하지 않고 사용법만 표시하는지, WordPress multisite 경고가 help에 포함되는지
  검사했다. Linux CI와 Docker/Cloudflare 실환경 동작은 별도 검증 대상으로 남는다.

## OD-009. 되돌리기 어려운 WordPress Multisite 전환을 service command로 제공하는 이유

- 상태: `seed`
- 관련 이력: `13616b7`, `df1b323`, `63437c8`
- 주제: `자동화할수록 더 신중해야 하는 WordPress Multisite 변환`
- 독자 질문: DB와 설정 파일을 함께 바꾸는 위험한 작업을 어떻게 자동화해야
  편리함이 데이터 손실 위험으로 바뀌지 않는가?
- 참고할 사항:
  - subdirectory multisite 전환은 단순 flag가 아니다. WordPress DB 상태,
    `wp-config.php`, Apache `.htaccess`, container의 실제 webroot가 함께 맞아야
    하며 콘텐츠 생성 뒤 single-site 복귀는 별도 migration이 된다.
  - `./opendock service wordpress multisite`는 실행 전 경고와 확인을 요구하고,
    `YES=1`은 의도적인 자동화에서만
    확인을 생략한다. 변경 전에 WordPress DB dump와 `wp-config.php`,
    `.htaccess`를 timestamp backup한다.
  - host에 WP-CLI를 설치하도록 요구하지 않고 WordPress CLI image를 사용했다.
    변환 뒤 container 환경에 맞는 Apache rewrite rule을 적용하고 서비스를
    restart한다.
  - Cloudflare Tunnel 뒤 HTTPS 인식 문제는 multisite URL 생성과 관리 기능에도
    영향을 줄 수 있어 proxy scheme 수정이 별도의 후속 작업으로 필요했다.
  - 처음에는 `action` dispatcher로 제공했지만, 범용어가 모호하다는 사용자
    피드백 뒤 `service` namespace로 정리했다. 위험한 동작을 서비스 소유 명령으로
    두면 공통 CLI에 WordPress 전용 top-level 명령을 추가하지 않아도 된다.
- 보존할 교훈:
  - destructive workflow 자동화의 품질은 실행 속도가 아니라 preflight,
    backup, 명시적 확인, 실패 지점, 복구 경로로 평가해야 한다.
- 검증 상태: subdirectory multisite workflow와 backup·confirmation 경계가
  구현되어 있다. 실제 콘텐츠가 있는 사이트의 역변환은 지원한다고 쓰지 않는다.

## OD-010. 로컬 Secret을 보내지 않는 실서버 rsync 배포 흐름

- 상태: `seed`
- 관련 이력: `c881d96`, `72c3cc5`
- 주제: `코드는 동기화하되 서버의 데이터와 Secret은 지키는 rsync 규칙`
- 독자 질문: Git 저장소를 실험 서버로 빠르게 보내면서 환경별 상태를 덮어쓰지
  않으려면 무엇을 제외해야 하는가?
- 참고할 사항:
  - 테스트 서버 반복 배포를 위해 처음에는 `.sync.env`의 target별 환경변수에
    remote, path, SSH port를 두고 Make 명령으로 sync했다. 변수명에 target을 붙여
    길게 조합하는 대신 `.sync.env.toml`의 `[targets.<name>]` 한 블록에 연결 정보를
    모으도록 바꿨다. `./opendock sync <name> --dry-run`은 target 이름과 설정을
    직접 대응시키며 TOML 표준 parser를 위해 Python 3.11+를 요구한다.
  - 실제 동기화 전에 `--dry-run`을 별도 명령으로 눈에 띄게 만든 것이 핵심
    안전장치다.
  - 초기 rsync는 `--delete`로 source에 없는 destination 파일을 제거할 수
    있었다. 실제 테스트/운영 환경에서 runtime 파일이 삭제된 것을 사용자가
    발견해 기존 exclude 목록만으로는 모든 host-owned 상태를 보호하기 어렵다는
    점이 드러났다.
  - 새 sync는 `git ls-files --cached --others --exclude-standard -z` 결과를
    `rsync --files-from=-`로 보내 tracked 수정 파일과 untracked 비무시 파일을
    함께 반영한다. `git add` 전 신규 코드도 테스트 서버에서 시험할 수 있고
    Git-ignored 파일은 보내지 않는다.
  - 전역 `rsync --delete`에 맡기지 않고 배포 파일 목록을 SSH로 전달해 원격
    디렉터리를 정리한다. source에 없는 원격 파일은 repository-owned로 간주해
    삭제하고, runtime·host-owned allowlist에 든 경로는 보존한다. 기존 원격의
    오래된 코드도 첫 실행부터 정리 대상이므로 `--dry-run`으로 미리 보여준다.
  - `.git`, 서비스 `data/`와 `backups/`, 정적 웹 콘텐츠, `common.env`,
    `*.env`, `domains.conf`, 생성된 Caddy routes, Supabase `functions.env`를
    보호한다. 이는 destination이 OpenDock checkout
    전용 경로라는 전제를 가지므로, 보호 목록 밖의 수동 원격 파일은 삭제될 수 있다.
  - `.env.example` 등 committed example은 배포 대상이며 실제 설정은 host state로
    남긴다. 새 runtime 경로를 추가하면 Git ignore와 sync 보호 목록도 함께 갱신해야 한다.
  - 설정 기본값 migration marker도 Git-ignore된 host state다. 사용자의 반복 setup
    출력에서 이전 migration 메시지가 다시 나타난 원인을 추적해 보니, 원격 prune
    보호 목록에서 marker가 빠져 있었다. `.service-default-migration-v1`,
    `.infra-default-migration-v1`, `.gateway-default-migration-v1`를 sync 보호 목록에
    추가해 이후 sync에서 보존하도록 했다. 사용자가 sync dry-run 및 실제 sync 후
    `./opendock setup mastodon`을 실행했고, 다른 서비스의 migration 메시지가
    반복되지 않는 것을 확인했다.
  - example 파일은 코드와 함께 보내 새 설정 항목을 발견하게 하지만 실제
    서버 Secret과 persistent data는 destination에 남는다. “설정 템플릿은
    배포 자산, 실제 설정은 host state”라는 경계다.
  - 새 generated field는 서버에서 다음 `make launch` 시 채울 수 있지만,
    도메인·Cloudflare·SMTP 같은 외부 값은 사용자의 검토가 필요하다.
- 보존할 교훈:
  - sync 자동화에서 include 대상보다 삭제로부터 보호할 host-owned state를
    먼저 정의해야 한다.
  - Secret 파일을 추가할 때 Git ignore만 수정하면 충분하지 않다. backup,
    sync, UI mount 등 모든 이동 경로를 함께 점검해야 한다.
  - 검증 상태: 사용자가 기존 sync로 runtime 파일 삭제를 실환경에서 확인했다.
    작업 트리 mirror와 remote prune 코드를 반영하고 CLI 검증 내용을 갱신했지만,
    테스트 실행과 dry-run/실제 sync 재확인은 아직 하지 않았다.

## OD-011. 도메인 라우팅을 앱 종류와 분리한 OpenDock 설계

- 상태: `seed`
- 관련 이력: `codex/feature/multi-domain-static-sites`,
  `codex/external-route-targets`,
  `scripts/opendock-domains.py`, `scripts/publish-cloudflare.py`,
  `gateway/caddy/conf.d/`, `static-sites/`
- 주제: `서비스 종류와 무관한 일관된 hostname route 모델 만들기`
- 독자 질문: 한 Gateway에서 설치된 서비스, 정적 파일, OpenDock 외부 앱을
  같은 도메인 관리 방식으로 어떻게 연결할 수 있는가?
- 참고할 사항:
  - 요구의 출발점은 이미 Docker WordPress를 쓰는 저사양 서버에 정적 사이트를
    추가하고 기존 사이트와 다른 도메인으로 공개하는 것이었다. 첫 구현안은
    Hugo 전용 설정으로 좁혀졌지만, 사용자가 요구를 “도메인별로 Docker 서비스나
    일반 static 서비스를 연결하는 OpenDock spec”으로 일반화했다. 특정 생성
    도구 대신 요구와 route target을 모델링한 판단을 중심으로 다룬다.
  - 내부 구현은 `domains.conf` 한 행에 hostname과 Docker 서비스 또는 static
    유형을 저장한다. `make setup`은 기본 도메인만 설정하고 hostname route는
    `make route show/add/remove`로 관리한다.
    `make launch <hostname>`이 신규 기본 UX이며, 서비스명 launch는 legacy다.
    파일이 없으면 기존 `STACK_DOMAIN`·subdomain 기반 라우팅을 유지한다.
  - 서비스별 Caddy 파일은 Docker upstream 동작을 정의하고,
    `opendock-domains.py`가 호스트별 Caddy site block을 생성한다. static target은
    Docker나 별도 웹서버 없이 Caddy가 read-only mount된
    `static-sites/<hostname>/` 파일을 직접 전달한다.
  - Cloudflare publishing은 hostname에 맞는 zone을 찾아 Tunnel ingress와 DNS를
    동기화한다. route remove는 해당 Tunnel ingress만 제거하고 DNS는 현재 Tunnel
    CNAME과 일치할 때만 지운다. Cloudflare 설정이 없으면 원격 정리는 건너뛴다.
    한 Tunnel에 연결하는 zone들은 같은 account여야 하며 token에 각 zone 권한이
    필요하다.
  - 사용자는 LM Studio API가 OpenDock 밖에서 실행되는 경우도 기존 Caddy reverse
    proxy 경로에 붙이고 싶어 했다. `route add <hostname> <service|static>` 문법을
    종류 우선의 `route add <type> <hostname> [<target>]`로 일반화하고 `static`,
    `service`, `external`을 공통 target 종류로 두는 방향을 선택했다. 새 예시는
    `route add external ai.example.org http://host.docker.internal:1234`다.
  - 구현에서는 `domains.conf`도 type-first line으로 바꾸고, 외부 upstream을 http/https
    origin으로 제한해 자격 증명·경로·query·fragment를 받지 않도록 했다. Caddy
    컨테이너가 upstream에 직접 연결하므로 host `localhost`와 Caddy container의
    `localhost`가 다르다는 점을 안내한다. external route launch는 upstream을 설치하거나
    시작하지 않고 gateway reload와 Tunnel/DNS publish만 수행한다. Cloudflare Tunnel은
    기존처럼 Caddy origin 하나로 연결되고 route type마다 Caddy가 내부 대상 처리를 맡는다.
  - `docs/routes.md`, root README, CLI root/route/add help에 같은 문법과 예시를 반영했다.
    이는 local implementation 상태이며 사용자 환경에서 실제 LM Studio reachability,
    Caddy reload, Cloudflare publication은 아직 확인하지 않았다.
  - `domains.conf`와 static web root는 host-owned 데이터로 보고 일반
    `make sync`에서 제외한다. 코드 배포 rsync가 원격 route 설정이나 사이트
    파일을 `--delete`로 지우지 않도록 한 경계다. 정적 콘텐츠는 서버에 별도로
    배포한다.
- 보존할 교훈:
  - 사용자 예시는 요구를 설명하지만 예시에 등장한 런타임이나 도구를 제품 계약에
    고정할 이유는 없다. 도메인과 route target을 먼저 모델링하면 Docker 앱과
    static 파일을 한 Gateway에서 일관되게 다룰 수 있다.
  - 자동 생성 설정은 기존 기본 동작을 보존하는 경로와 명시적 편집을 시작하는
    전환점을 함께 제공해야 한다.
- 검증 상태: hostname 중심 CLI와 문서 변경은
  `codex/feature/multi-domain-static-sites`에서 진행 중이다. `make help`와
  `git diff --check`는 확인했지만 테스트나 Caddy 설정 검증을 실행하지 않았으며,
  로컬 runtime 및 실제 Cloudflare zone/Tunnel 경로는 아직 검증되지 않았다. External
  route 후속 구현은 Python 정적 컴파일, CLI help 출력, `git diff --check`를 확인했다.
  Test suite, Caddy config adaptation, 실제 외부 upstream과 Cloudflare Tunnel은 아직
  검증하지 않았다.

## OD-012. Make를 호환 계층으로 줄이고 Python CLI를 사용자 접점으로 만든 이유

- 상태: `seed`
- 관련 이력: `codex/feature/python-cli`, `Makefile`, `opendock`,
  `tests/test_cli.py`, `.github/workflows/cli.yml`
- 주제: `Makefile 421줄에서 ./opendock으로: 홈서버 운영 명령의 경계 재설계`
- 독자 질문: Docker Compose, 도메인 라우팅, Cloudflare, 배포를 한 명령 체계로
  다룰 때 Make는 어디까지 적합하고 언제 전용 CLI가 필요한가?
- 참고할 사항:
  - 사용자 접점이 `make setup`, `make route add <host> <type>`, `make launch
    <hostname>`, `make sync <remote>`로 늘었다. Make의 목표를 위치 인자로
    해석하고 나머지 목표를 no-op으로 삼는 구조는 명령 검증과 오류 안내를
    어렵게 했다. 실패할 때 OpenDock 안내 뒤에 Make 자체의 Error 문구가
    붙는 경험도 문제를 선명하게 했다.
  - just와 Task는 작업 실행기 대안이지만, 사용자가 원하는 계층적 명령과
    인자 검증에는 이미 프로젝트가 사용하는 Python 표준 라이브러리
    argparse가 더 맞는다고 판단했다. 저장소 루트의 실행 파일로 두어 별도
    설치 단계 없이 `./opendock`을 사용한다.
  - 기존 설정·도메인·Cloudflare Python 스크립트를 재사용하며 Compose
    호출 순서, post-launch hook, host-owned sync 제외 규칙을 CLI로 옮겼다.
    Makefile은 과거 명령을 새 CLI로 전달하는 호환 계층으로 남겼다.
  - Linux와 macOS를 모두 목표로 하므로 Ubuntu bootstrap과 README에 Python 3.11+
    요구사항을 명시하고, 두 OS의 Python 3.11에서 CLI 테스트 matrix를 실행하도록
    했다. shebang만으로
    Python 설치나 외부 명령의 가용성이 보장되는 것은 아니다.
  - 첫 CLI의 argparse 기본 도움말은 모든 명령을 한 줄에 나열해 시작 흐름이
    보이지 않았다. 사용자 피드백 후 `--help`, `help`, 인자 없는 실행은
    `setup → launch → list`와 도메인·운영·배포 용도별 안내를 먼저 보여주고,
    개별 명령의 `--help`는 argparse의 정확한 인자 설명을 유지했다.
- 보존할 교훈:
  - zero-config CLI는 명령어를 짧게 만드는 일뿐 아니라 의존성 안내,
    오류 상태, 기존 명령과의 전환 경로까지 포함한다.
  - task runner를 교체하는 문제와 운영 제품의 사용자 인터페이스를 설계하는
    문제를 구별해야 한다.
- 검증 상태: macOS에서 CLI 단위 테스트, 재구성된 도움말, 목록 및 호환 Make 호출을
  로컬 검증했다. Ubuntu CI matrix는 추가했지만 아직 실행 결과를 확인하지
  않았다. Docker 기동과 실제 Cloudflare 게시의 새 CLI 경로는 실환경 검증 전이다.

## OD-013. Hermes의 Docker sandbox를 Docker 안에서 구동할 때의 경계

- 상태: `seed`
- 관련 이력: `codex/feature/hermes-agent`, `services/hermes/compose.yml`,
  `services/hermes/README.md`, `opendock`, `gateway/caddy/conf.d/hermes.caddy`
- 주제: `Agent 명령은 sandbox에서 실행하면서 Docker socket은 왜 필요한가?`
- 독자 질문: Agent 자체를 Docker 컨테이너로 운영하면서 명령 실행을 별도
  컨테이너로 격리하려면 Docker API 권한, 파일 경로, 웹 인증을 어떻게 다뤄야 하나?
- 참고할 사항:
  - 사용자는 Oracle 저사양 서버가 아닌 Apple Silicon macOS 노트북과 Linux를
    대상으로 Hermes Agent를 OpenDock 서비스로 운영하고, 웹 dashboard를
    hostname으로 쓰며, agent 명령은 별도 Docker sandbox에서 실행하기를 원했다.
  - Hermes의 Docker terminal backend는 지속되는 sandbox 컨테이너를 만들고
    tool 명령을 그 안에서 실행한다. Hermes runtime은 이를 제어하기 위해
    Docker socket을 사용한다. sandbox에서 실행되는 일반 tool 명령과 runtime의
    Docker daemon 권한은 서로 다른 경계이며, runtime 또는 socket이 침해되면
    OpenDock Docker 엔진의 컨테이너와 volume을 제어할 수 있음을 문서화했다.
  - Docker daemon은 bind mount 경로를 Docker client 컨테이너가 아니라 host에서
    해석한다. 그래서 sandbox 데이터 디렉터리를 host와 Hermes 컨테이너 안에서
    같은 절대경로로 공유하고, `opendock`에서 socket GID와 sandbox 경로를 주입한다.
  - Dashboard는 Caddy hostname route와 기본 인증을 구성하고, 공개 hostname에는
    추가 identity-aware access 계층을 권한다. Hermes 공식 문서는 기본 사용자명/
    비밀번호 제공자가 trusted LAN 또는 VPN용이라고 구분한다.
  - `HERMES_VERSION`은 mutable `latest` 대신 stable tag로 고정하고 Renovate의
    dotenv custom manager가 `common.env.example`의 marker를 추적하게 했다.
  - 첫 실제 onboarding에서는 `HERMES_*` 값이 비어 Compose가 빈
    `container_name`으로 실패했다. preflight를 넣어 OpenDock 설정 누락을 먼저
    설명하게 했지만, 이어 실행한 `setup hermes`가 `Nothing changed`라고 끝났다.
    원인은 Secret target 목록에는 Hermes 키가 있었으나 `generate_values()`에
    실제 생성 규칙이 없어 placeholder를 갱신하지 못한 것이었다. dashboard
    password와 세션 서명 키 생성을 generator에 추가했다.
- 보존할 교훈:
  - containerized agent의 “명령 격리”와 “container runtime 권한 격리”를 같은
    것으로 설명하면 안 된다. Docker socket은 편의성뿐 아니라 신뢰 경계를 바꾼다.
  - nested Docker 제어에서 host bind mount 경로의 관점은 container 내부가 아니라
    daemon이 실행되는 host라는 점을 고려해야 한다.
- 검증 상태: 사용자가 Linux 환경에서 onboarding의 빈 Compose 변수 실패와
  `setup hermes`의 잘못된 `Nothing changed` 결과를 확인했다. generator 수정은
  반영했지만 재실행으로 Secret 생성과 onboarding 성공을 확인하기 전이다.
  테스트나 Docker 기동을 실행하지 않았고 macOS/Linux runtime, dashboard 로그인,
  Cloudflare Access, sandbox mount 동작은 미검증이다.

## OD-014. 첫 실행은 자동화하고 재설정은 명시하는 zero-config CLI

- 상태: `seed`
- 관련 이력: 현재 `codex/feature/hermes-agent` 작업,
  `AGENTS.md`, `opendock`, `services/hermes/commands/onboard`,
  `services/hermes/README.md`
- 주제: `첫 실행은 launch 하나로, 반복 설정은 명시적인 명령으로`
- 독자 질문: 서비스의 첫 실행 준비를 자동화하면서도, 사용자가 나중에
  설정을 다시 바꿀 통제권은 어떻게 남길 수 있는가?
- 참고할 사항:
  - OpenDock은 Hermes 전용 앱이 아니라 여러 앱과 공유 infra를 운영하는
    플랫폼이다. Hermes의 Docker sandbox 자체는 별도 사용자 설정이 필요하지만,
    shared network와 platform infra는 OpenDock이 준비할 수 있는 선행 작업이다.
  - 초기 안내가 `setup hermes` 다음 별도 `service hermes onboard`, 이어
    `launch`를 요구해 사용자는 순서와 명령 구분을 이해해야 했다. 목표 흐름은
    `./opendock launch hermes` 하나가 누락된 OpenDock 설정을 묻고, infra를
    올리고, 최초 Hermes 설정 후 dashboard 서비스를 시작하는 것이다.
  - 상세 경로인 `./opendock setup hermes`도 OpenDock 값을 설정한 뒤 최초
    Hermes onboarding까지 진행한다. 다만 이미 모델이 설정된 경우에는 wizard를
    반복하지 않는다. 모델 상태 확인은 Hermes의 `config get model`에서
    기본 모델 항목을 읽도록 설계했다.
  - 첫 Hermes launch가 infra를 올린 다음 한동안 멈춘 것처럼 보였다. 상태 확인이
    `docker compose run ... config get model`로 image를 처음 pull할 수 있는데,
    해당 probe가 Compose stderr까지 숨기고 있었다. launch 전에 probe 단계를
    출력하고 Compose 진행 상태를 사용자에게 보이도록 바꿨다.
  - 사용자가 `remove hermes` 결과에서 `hermes_hermes_data` 제거를 확인한 뒤
    launch했지만 onboarding이 건너뛰어졌다. 로그에는 모델 조회용 `compose run`이
    새 볼륨을 먼저 만들고, 그 뒤 모델이 이미 설정됐다고 판정한 순서가 남았다.
    따라서 첫 실행에서는 조회용 컨테이너를 띄우기 전에 볼륨 존재 여부를 확인하고,
    볼륨이 없으면 곧바로 wizard를 실행하도록 보완했다. 이미지 초기화가 새 상태에
    무엇을 쓰는지는 실제 서버에서 수정 후 다시 확인해야 한다.
  - upstream provider나 messaging integration을 나중에 바꾸려는 의도적인
    재설정 경로로 `./opendock service hermes onboard`를 유지한다. 따라서 보통의
    첫 실행은 간단하지만 기존 사용자가 다시 설정할 수 있는 수단도 남는다.
  - dashboard username/password는 Hermes model onboarding 값과 별도다. Compose가
    `services/hermes/.env`의 값을 컨테이너 시작 때 Basic Auth 환경변수로 전달하므로
    private runtime config에 보존해야 한다. 사용자가 password를 직접 입력하길 원해
    자동 생성에서 마스킹 입력으로 바꾸고, 바뀐 값을 적용하려면 컨테이너 재생성이
    필요하다는 점을 안내한다. 내부 session-signing secret은 계속 자동 생성한다.
  - 기본 route 파일에 Hermes 항목이 빠져 있어도 `launch hermes`가 서비스의
    default hostname을 추가하도록 해, launch가 성공했는데 공개 route가 없는
    상태를 피한다.
- 보존할 교훈:
  - zero-config는 설정 질문을 없애는 것이 아니라 사람이 정해야 하는 값만
    첫 실행에서 묻고, 반복 가능한 준비는 자동화하며, 완료 여부를 저장 상태에서
    확인하는 것이다.
  - 최초 setup과 의도적인 재설정은 서로 다른 작업이다. 하나의 명령이 매번
    인터랙티브 wizard를 띄우면 자동화와 일상적인 설정 변경이 충돌한다.
  - shared infra는 서비스 내부의 부수 작업이 아니라 플랫폼이 처리하는
    prerequisite로 보여줘야 한다.
  - 검증 상태: macOS에서 CLI/unit test 27개가 통과했다. 사용자는 Linux 테스트
    서버에서 기존 remove/launch를 수행했고 볼륨 제거 및 probe 직후 onboarding skip을
    관찰했다. 볼륨이 없는 경우 probe를 생략하는 수정은 아직 테스트 서버에서 확인
    대기 중이며, 반복 launch의 skip 동작과 custom hostname 공개도 재확인이 필요하다.

## OD-015. 서비스 추가만큼 중요한 제거 계약 설계

- 상태: `seed`
- 관련 이력: 현재 `codex/feature/hermes-agent` 작업, `AGENTS.md`,
  `config/README.md`, `scripts/opendock_settings.py`, `opendock`,
  `scripts/opendock-remove.py`, `tests/test_settings.py`, `tests/test_remove.py`,
  `services/hermes/compose.yml`, `infra/compose.yml`
- 주제: `up의 반대 명령 하나로는 왜 self-hosted 앱을 안전하게 제거할 수 없나`
- 독자 질문: 컨테이너, 이미지, 서비스 DB, 업로드 파일, route가 서로 다른
  소유권과 저장 위치를 가질 때 공통 제거 명령의 안전한 범위를 어떻게 정할까?
- 참고할 사항:
  - OpenDock에는 `stop`과 `down`이 있지만 `down`은 컨테이너를 제거하면서
    persistent data를 보존한다. 서비스의 데이터를 포함해 처음 상태로 되돌리는
    공통 `remove` 명령은 아직 없다.
  - Compose 볼륨, 저장소 아래 bind mount, 서비스 전용 database/schema,
    재생성 가능한 cache는 같은 `data/` 개념이 아니다. 예를 들어 Immich는 사진
    library와 Postgres data 경로를 함께 두고, Supabase는 DB와 Storage를 bind
    mount하며 Deno cache를 별도 named volume으로 둔다.
  - WordPress·Mastodon·Mattermost·Nextcloud는 OpenDock shared database를
    사용하므로 Compose 프로젝트의 볼륨 제거만으로 앱을 reset할 수 없다.
    반대로 shared DB volume을 삭제하면 무관한 앱까지 손실된다.
  - `jellyfin/media`, `immich/data/library`, WordPress webroot와 같은 경로는
    앱이 관리하는 상태와 사용자가 보관한 콘텐츠가 섞일 수 있어 무조건 삭제할
    대상으로 취급하지 않는다. route와 static site 콘텐츠도 별도 소유권이다.
  - 사용자는 provisioning 명령의 대응 동작으로 설정·컨테이너·이미지·볼륨
    제거를 원했고, 기본 `purge <service>`를 전체 제거로 해석하되 확인을
    의무화하는 안을 선택했다. `stop`과 `down`은 기존의 좁은 범위 작업으로
    유지하고, 전체 제거 전 서비스 소유 자원 목록을 보여주는 방향이다.
    이 계약은 새 서비스뿐 아니라 명령 출시 전에 현재 서비스 모두에 소급
    적용해야 한다.
  - `-p hermes` 프로젝트의 Compose logical volume `hermes_data`는 실제 Docker
    volume 이름에서 project prefix를 받을 수 있다. 이 이름을 사용자에게 직접
    요구하지 않고 Compose 선언과 서비스별 cleanup metadata로 해석하는 편이
    안정적이다.
  - Hermes pilot에서는 `remove hermes`가 전체 제거로 동작하고, 삭제 전에
    `REMOVE hermes`를 직접 입력하게 했다. `--dry-run`은 동일한 자원 계획을
    출력하고, 비대화형 호출과 잘못된 확인은 삭제하지 않는다.
  - Compose project의 컨테이너·named volume과 Compose 해석 이미지 목록을
    조회한다. Hermes sandbox 컨테이너는 `hermes-task-id` label만으로 전부
    지우지 않고, OpenDock이 지정한 sandbox bind path를 실제 mount한 컨테이너만
    제거한다. image는 다른 container에서 사용 중이면 강제로 제거하지 않는다.
  - Hermes route는 Cloudflare Tunnel/DNS에서 먼저 제거하고 domains.conf와 Caddy를
    갱신한다. 서비스 기본값은 `services/hermes/.env.default`, 실제 설정과 비밀값은
    `services/hermes/.env`에 귀속시키고 삭제 전 permission 제한 backup을 남긴다.
    core domain, shared mail, infra 설정과
    repository 코드는 보존한다.
  - 초기에는 root `common.env`가 global domain, SMTP, shared DB 관리자 계정,
    서비스별 암호와 hostname을 한 파일에 함께 소유했다. 제거 코드가 키 이름으로
    설정을 지우는 방식은 명시적 소유권이 없으면 실수하기 쉽다는 점을 드러냈다.
    `scripts/opendock_settings.py`에 key-to-owner 규칙을 두고 core/infra/shared/
    service 예시와 private override를 나눴으며, 기존 파일은 소유자별로 이전한 뒤
    제한된 백업으로 보존한다. 모르는 키가 있으면 원본을 변경하지 않고 중단한다.
  - 지원 등록되지 않은 서비스는 제거를 거부한다. 이 pilot은 Hermes만 켜고,
    다른 서비스는 각 데이터·공유 DB 범위를 검토한 후 순차적으로 등록한다.
- 보존할 교훈:
  - 설치 절차만큼 제거 계약도 서비스 정의의 일부다. 새 서비스는 persistent
    state, 사용자 콘텐츠, 공유 DB 객체와 route의 소유권을 함께 설명해야 한다.
  - `remove`는 공통 UX를 제공할 수 있지만 삭제 작업 자체는 service-aware여야
    한다. `services/<name>/data`를 통째로 지우는 규칙은 안전하지 않다.
  - 기본 전체 제거는 `down`과 구분되는 명확한 의미를 가져야 하며, 삭제 목록과
    확인 없이 실행되면 안 된다.
- 검증 상태: Python 3.15.2에서 21개 CLI/unit test가 통과했다. 설정 owner 분류,
  기존 `common.env` 이전과 backup, 미등록 키의 fail-safe, Compose env 파일 순서와
  선택 범위, Hermes 제거 계획·확인·route 분리·임시 디렉터리 내 삭제 순서를
  검사했다. Docker socket 접근이 거부되어 실제 Compose volume/image 제거,
  sandbox container discovery, Cloudflare API와 test server 재기동 검증은 남아 있다.

## OD-016. 설정 파일을 기능이 아니라 소유권으로 나누기

- 상태: `seed`
- 관련 이력: `codex/feature/hermes-agent`, `AGENTS.md`, `config/README.md`,
  `scripts/opendock_settings.py`, `scripts/opendock-config.py`,
  `scripts/opendock-secrets.py`, `services/hermes/.env.default`,
  `tests/test_settings.py`, `renovate.json`
- 주제: `common.env` 하나를 core·공유 인프라·서비스별 설정으로 나누면서
  Renovate와 사용자 override를 어떻게 유지할까
- 독자 질문: 여러 Docker 서비스를 관리하는 CLI에서 기본값, 비밀값, 운영자
  선택, 공유 인프라 값을 어떤 파일 구조로 소유시키면 업데이트와 제거가 쉬울까?
- 참고할 사항:
  - OpenDock의 기존 `common.env`는 primary domain, SMTP, database 관리자
    credential, 각 서비스의 image/tag·hostname·비밀값을 한데 섞었다. 설정을
    수집하거나 서비스 제거를 구현할 때 키 소유자가 불분명했다.
  - 사용자는 서비스 디렉터리에 있는 버전 기본값과 Renovate 동작을 유지하면서,
    host별 override와 비밀값은 Git/Renovate 밖에 두고 싶어 했다. 합의된 설계는
    `config/core.env.default`/`config/core.env`, `config/infra.env.default`/
    `config/infra.env`, `config/shared/<concern>.env.default`/실제 `.env`, 그리고
    서비스의 `services/<service>/.env.default`/실제 `.env`다.
  - Hermes를 먼저 옮긴다. `HERMES_*` key owner는 `services/hermes/.env`이고,
    platform core·infra·mail은 config 계층에 남는다. 그 외 서비스는 아직 기존
    `config/services/<service>.env.example`, private override, tracked runtime
    `.env`에 두고 Hermes 검증 이후 하나씩 바꾼다. 기존 tracked `.env`는 전환까지
    Renovate 대상으로 유지한다. Git ignore 규칙은 migrated local `.env`만 제외한다.
  - `scripts/opendock_settings.py`를 공통 loader/writer로 두고 setup, secret
    생성, validation, Compose interpolation 및 route 코드는 같은 계층 병합 규칙을
    공유한다. Compose는 `.env.default` 다음 실제 `.env`를 명시적으로 전달하며,
    override를 지우면 다시 업데이트 가능한 default를 쓴다.
  - Hermes pilot 이후 다른 서비스도 같은 경계로 옮겼다. tracked 서비스 `.env`의
    image/version·container defaults와 `config/services/*.env.example`의 사용자
    설정/secret placeholders를 하나의 `services/<service>/.env.default`로 합쳤다.
    중복 사용하던 MariaDB client image version은 shared database config로 승격했다.
    기존 private `config/services/*.env` 값은 서비스 소유 `.env`로 이동하고
    restrictive backup을 남기도록 초기화 migration을 확장했다.
  - 첫 실제 적용 흐름에서 공용 infra 이미지 버전은 `infra/.env`에 남아 있었고,
    config validator는 해당 경로를 로드하지 않아 Hermes launch의 infra 사전검사가
    `MARIADB_VERSION`, `POSTGRES_VERSION`, `REDIS_VERSION` 누락으로 실패했다. 세 버전을
    `config/infra.env.default`로 이동하고, 기존 파일의 비기본값만 private config로
    옮기는 migration을 추가했다. 이로써 서비스뿐 아니라 infra도 같은 default/private
    소유권 규칙을 따라야 함을 확인했다.
  - 전체 경로 감사에서 gateway의 Caddy 버전과 포트도 tracked `gateway/.env`에
    남아 있어 `.env.default`만 검사하는 Renovate 규칙에서 빠지고, Compose 실행 때만
    별도로 읽히는 점을 확인했다. 이를 `config/gateway.env.default`/`config/gateway.env`
    로 옮기고, Caddy 컨테이너에 불필요한 `env_file` 주입과 CLI 정보 표시의 직접
    `.env` 파싱을 제거해 설정 로더를 단일 기준으로 맞췄다.
  - root `common.env`는 알려진 key를 owner 파일로 옮기고 제한 권한 백업을 남기는
    일회성 migration 입력이다. 알 수 없는 key가 있으면 원본을 바꾸지 않는 fail-safe를 둔다.
- 보존할 교훈:
  - 계층 이름(core/infra/service)만으로 파일을 나누지 말고 각 key의 소유자와
    소비자를 먼저 등록해야 한다. 공유 설정과 서비스 설정은 lifecycle도 다르다.
  - Renovate는 실제 사용자 `.env`를 읽게 하지 말고 tracked `.env.default`만
    갱신해야 한다. 구형 tracked `.env`는 버전 정보를 옮긴 뒤 더 이상 추적하지 않는다.
  - 모든 서비스를 한 번에 이동하지 않고 실제 서비스 하나를 pilot으로 골라
    setup, secret 생성, config validation, Compose, 제거, Renovate 경로를 확인한
    뒤 다음 서비스로 넓힌다.
  - 검증 상태: macOS Python 3.15.2에서 설정 테스트 34개가 통과했다.
    `./opendock check-config infra`와 `gateway`가 모두 `OK`를 반환했다.
    `./opendock info gateway`는 `caddy:2`를 표시했지만 Docker socket 접근이
    거부되어 실행 중인 컨테이너 상태는 확인하지 못했다. 각 기존
    서비스의 이전 추적 `.env`와 example key를 새 `.env.default`와 대조해 누락/추가
    key가 없음을 확인했고, bytecode compile, Renovate JSON parse, `git diff --check`도
    통과했다. Linux host의 private config migration, 각 서비스 Compose rendering 및
    Renovate PR 인식은 실제 서버/Cloud app에서 확인하기 전까지 미검증이다.

## OD-017. 공통 CLI와 서비스별 동작의 책임 경계

- 상태: `seed`
- 관련 자료: `docs/command-architecture.md`, `AGENTS.md`, `opendock`,
  `scripts/opendock-config.py`, `scripts/opendock_settings.py`,
  `scripts/opendock-remove.py`, `scripts/opendock-service.py`,
  `scripts/opendock_capabilities.py`, `scripts/opendock_catalog.py`,
  `scripts/opendock-secrets.py`, `scripts/check-config.py`,
  `services/hermes/opendock.toml`, `services/wordpress/opendock.toml`,
  `services/supabase/opendock.toml`, `services/mastodon/opendock.py`,
  `services/supabase/opendock.py`, `scripts/opendock-service.py`,
  `services/extensions/mastodon/opendock-post-start.py`,
  `services/extensions/supabase/opendock-post-start.py`
- 주제: `서비스가 늘어도 CLI dispatcher가 비대해지지 않게 하려면`
- 독자 질문: 공통 명령의 일관성을 유지하면서 setup, launch, remove의 서비스별
  차이를 어디에 두어야 하는가?
- 참고할 사항:
  - OpenDock은 Compose 파일을 기준으로 service target을 탐색하고,
    `services/<name>/commands/`의 실행 가능한 파일로 service 명령을 탐색한다.
    Mastodon과 Supabase에는 기존 post-launch hook도 있다. 즉, 서비스 디렉터리에서
    기능을 발견하는 선례는 이미 있다.
  - 초기에는 Hermes 온보딩과 모델 상태 판정이 중앙 `opendock`에 있었고,
    setup field, DB dependency set, 일부 credential 안내는
    `scripts/opendock-config.py`에 있었다. Mastodon/Supabase validation과 Supabase
    JWT key bundle 생성도 중앙 `scripts/check-config.py`와
    `scripts/opendock-secrets.py`에 있었다. 흩어진 방식 때문에 어느 지식이 공통이고
    어느 지식이 서비스 소유인지 한눈에 알기 어려웠다.
  - 첫 remove 작업을 서비스 등록표와 manifest로 넓히려던 중, remove만 분리하면
    setup과 launch에 같은 중앙 분기를 계속 추가하게 된다는 문제를 발견했다.
    그래서 command family 전부를 중앙 orchestration과 service capability로 나누는
    설계 문서를 먼저 작성했다.
  - 경계 기준은 플랫폼 invariant와 공통 순서는 core가 소유하고, 애플리케이션
    상태·데이터 모델에 의존하는 판단은 서비스가 소유하며, 재사용 가능한 mechanism은
    core가 제공하고 서비스별 입력은 서비스가 선언하는 것이다. 공유 자원과 다른
    서비스 상태는 플랫폼 소유로 남는다.
  - 설계안은 선언형 service descriptor와 optional typed Python capability로 구성한다.
    setup schema, dependency, route metadata, resource ownership은 descriptor에 두고,
    Supabase secret bundle이나 Hermes onboarding처럼 application logic이 필요한 것은
    capability로 둔다. Core가 persistence, confirmation, output, platform operation을
    통제하고 capability에는 필요한 scope의 API만 주어 private CLI 함수나 다른
    서비스 구현에 의존하지 않게 한다.
  - 기존 plugin 구조를 참고해 service 단위와 ID 규칙, descriptor/API version 분리,
    capability discovery, runtime remove와 source deregistration 분리를 추가했다.
    Terraform의 Core/provider 경계와 versioned protocol, plan/apply 구분, Ansible
    Collections의 namespaced content 구성을 참고하되, 서비스가 한 저장소에서 함께
    배포되는 현재 조건에는 별도 gRPC 프로세스와 패키지 registry를 도입하지 않는다.
    Python entry points도 설치 배포물 검색용이므로 지금의 폴더 기반 catalog와는
    목적이 다르다.
  - 현재 branch에서는 `scripts/opendock_catalog.py`가 `services/*/compose.yml`를
    발견하고 인접한 `opendock.toml`의 schema/API version, capability, dependency를
    검증한다. target/setup/config/secrets/domain/publish의 service discovery도 이
    catalog를 공유하도록 옮겼다.
  - Hermes는 `services/hermes/opendock.toml`과 `opendock.py`를 통해
    `runtime_environment` 및 `prepare` capability를 선언한다. 중첩 Docker sandbox의
    환경값과 first-run model onboarding 판정을 서비스 소유 코드로 이동했다.
    Mastodon/Supabase 후속 작업도 descriptor가 `post_start`를 선언하고
    서비스 capability handler를 거치도록 바꿨다. helper 파일명만으로 자동 실행되는
    경로는 제거했다.
  - 기본 hostname은 서비스 ID에서 `<SERVICE>_SUBDOMAIN`과 Caddy snippet 이름을
    추측하던 방식에서 descriptor의 `routing.subdomain_key` 및 `routing.caddy_handler`로
    옮겼다. resolver는 routing을 선언한 service만 기본 public route 대상으로 삼는다.
    이어서 모든 현재 Compose 서비스에 descriptor를 추가하고 setup field와
    MariaDB/PostgreSQL 공유설정 요구를 그 안에 선언했다. 공통 setup prompt가
    선언을 읽으며, Uptime Kuma는 custom handler가 없어도 descriptor만으로 등록되는
    단순 서비스 예가 됐다.
  - capability API v1은 좁은 service-scoped context와 typed 결과를 제공한다.
    준비와 runtime environment뿐 아니라 `plan_secrets`, `generate_secrets`,
    `validate_config`를 연결했다. secret field와 generator ID는 descriptor에 선언하고,
    application-specific bundle 생성·교차값 검증은 서비스 handler에 둔다. 중앙은
    공통 generator, 실행 시점 조정, 안전한 저장과 결과 표시를 맡는다. `setup`은
    설정 과정에서, `launch`는 config 검사 전, `secrets`는 명시적 복구 경로로
    같은 coordinator를 사용한다. Supabase의 초기 functions.env 준비도 해당 서비스의
    `prepare` capability로 옮겼다. 이 구조는 신뢰된 checkout의 Python 코드이며
    보안 sandbox가 아니라는 경계도 문서에 기록했다.
  - 사용자가 실제 n8n 첫 launch에서 OpenDock이 완료 링크를 출력한 뒤에도
    Cloudflare gateway 오류, `/get`, setup 화면이 차례로 나타나며 오래 걸리는 것을
    관찰했다. Compose `--wait`는 컨테이너 실행/선언된 healthcheck까지만 확인하므로
    애플리케이션 bootstrap 완료와 같지 않다는 점을 기준으로 삼았다. 단계 이름을
    `prepare`(설정·비밀값·저장소·공유 prerequisite·서비스 준비), `start`(서비스 Compose
    기동 확인), `launch`(gateway와 public route 게시)로 분리했다. Descriptor에는
    선택적 `[lifecycle.messages]`의 `pre_prepare`/`post_prepare`, `pre_start`/`post_start`,
    `pre_launch`/`post_launch` 여섯 메시지 지점을 두고, 선언되지 않은 지점은 출력하지
    않는다. 실행 action은 `prepare`와 Compose 기동 후 route 게시 전의 `post_start`로
    구분한다. 이전 `post_launch` action 이름은 pre-release라 호환 alias 없이 없앴다.
    n8n v2/v3는 `pre_start`에서 느린 첫 구동을 예고하고 `post_launch`에서 route 게시 뒤에도
    bootstrap이 계속될 수 있음을 알린다. Uptime Kuma는 별도 hook/message가 없어도
    descriptor가 유효한 단순 서비스 예로 남는다. 앱별 readiness는 별도 판정 방식과
    timeout 계약이 필요하므로 다음 단계로 미뤘다.
  - Hermes 제거 기능은 중앙 전용 코드에서 공통 제거기로 전환하고, `[removal]`
    descriptor에 `data/sandboxes`, 추가 sandbox 이미지, 컨테이너 label과 소유 mount
    path를 선언한다. 공통 제거기는 이 선언을 확인해 Compose 자원,
    라우트, 서비스 설정과 함께 계획한다. 다음으로 Uptime Kuma는 영속 데이터가
    Compose named volume 하나에 있고 host bind path나 shared DB가 없음을 확인해 두 번째
    제거 대상으로 등록했다. complete remove가 monitor와 notification 설정을 지운다는
    안내를 README에 추가했다. 이 시점에는 shared DB 오브젝트 처리가 미지원이었다.
    Homepage는 Compose bind mount가 삭제하면 안 되는 Git 관리 설정임을 확인해
    data deletion 목록에서 제외했다. 제거 시 Homepage config는 보존되고 컨테이너,
    이미지, route, private 설정만 제거하도록 세 번째 계약을 등록했다.
    n8n은 workflows, credentials, encryption keys, execution 데이터가 named volume에만
    있음을 확인해 해당 volume을 지우는 완전 제거 계약을 추가했다.
    Immich는 별도 Postgres 컨테이너와 bind-mounted DB, 업로드된 사진·영상 library,
    model cache volume을 사용하므로 이 세 데이터 범주를 제거 계획에 드러내고 삭제 경고를
    문서화했다.
    Supabase는 DB/storage bind data 외에 Git에서 제외된 `functions.env`를 사용한다.
    이를 descriptor의 private `config_files`로 선언하고, 공통 remover가 삭제 전에
    restrictive backup을 남기는 처리를 추가했다. 추적되는 Edge Function source와 config는
    제거 대상에서 뺐다.
    Jellyfin media 디렉터리에는 Git 관리 `.gitkeep` placeholder가 있어 사용자 미디어를
    삭제하면서도 checkout을 변경하지 않도록 descriptor `preserve_paths`와 공통 선택적
    tree cleanup을 추가했다.
    마지막 네 서비스는 shared MariaDB/PostgreSQL을 함께 쓰므로 infra descriptor에 DB
    실행 어댑터를 선언하고, 각 서비스 descriptor에 자기 database/role setting key를
    선언했다. DB별 실행 SQL은 infra의 `adapters/`로 옮겼다. 공통 계획은 다른 dependent
    service의 선언과 이름 충돌을 확인하고, descriptor가 선택한 adapter로 database/role만
    삭제해 shared volume과 다른 DB를 보존한다. 이로써 현재 11개
    Compose 서비스 모두 removal contract를 선언했다. 이는 코드/메타데이터 상의 범위이며,
    실제 clean host에서 서비스별 삭제 전후와 타 서비스 보존을 확인하는 전체 acceptance pass는
    아직 수행하지 않았다.
  - 추가 명령의 help 설명도 중앙 `COMMAND_HELP` 표에서 서비스 descriptor의
    `[[commands]]`로 옮겼다. Hermes, WordPress, Supabase가 자신의 명령 이름,
    설명, 실행 예를 소유하고 common dispatcher는 파일 탐색과 공통 렌더링만 담당한다.
  - 공통 MariaDB/PostgreSQL secret 정의와 setup target 분기를 중앙 스크립트에서
    반복하지 않도록 `infra/opendock.toml`에 infra 소유 setting key, shared group,
    setup field와 secret generator를 선언했다. Service catalog는 platform descriptor의
    shared group을 기준으로 service dependency를 검증하고, setup/secrets는 서비스가
    선언한 group에서 infra field를 선택한다. 설정 owner 경로도 infra descriptor의
    setting key 목록에서 파생된다. 당시 `MARIADB_CLIENT_VERSION`은 infra의 shared
    setting으로 database env 파일 소유자와 `mariadb` dependency 조건을 선언했다. 따라서
    legacy 서비스 설정 migration도 같은 선언을 참고했다. 이후 mail metadata와의 위치
    일관성을 위해 shared setting 선언을 `config/shared/database.toml`로 옮겼다. 이어 gateway setting key도
    `gateway/opendock.toml`로 옮겼다. SMTP 설정은 `config/shared/mail.toml`에 key,
    owner file, setup field를 선언하고 common setup/settings workflow가 읽도록 바꿨다.
    `STACK_DOMAIN`도 `config/core.toml`로 옮겨 core owner와 placeholder를 선언한다.
  - 설정 migration의 WordPress·Nextcloud 조건은 서비스 이름을 직접 비교하는 대신
    각 서비스 descriptor의 shared MariaDB dependency를 기준으로 일반화했다.
    Mastodon 예약 username 판정은 setup helper에서 제거해 Mastodon validator가
    소유한다. Sync에서는 일반 `.env` 제외 규칙과 겹치는 Supabase 전용 예외를 제거했다.
  - 사용자는 첫 catalog/capability 적용 후 `./opendock --help`, `./opendock list`,
    `./opendock launch hermes` 경로와 이어서 `./opendock setup hermes` 동작을
    확인했다. 두 번째 실행에서는 기존 onboarding을 건너뛰었다. 이후 모든 서비스의
    setup 필드와 공유 설정 dependency를 descriptor로 옮기고, 같은 설정값을 다시
    private `.env`에 쓰지 않도록 수정했다. 사용자는 원격 개발 환경에서 `sync` 후
    `setup mastodon`을 다시 실행했고, 기본값 migration 메시지가 반복되지 않는 것을
    확인했다. secret/validation capability 연결은 코드에 반영했지만 아직 실환경에서
    확인하지 않았다. 깨끗한 데이터에서의 첫 onboarding과 Linux/macOS 양쪽 검증도
    남아 있다.
  - 이번 후속 정리에서는 post-launch capability, routing metadata, infra DB adapter,
    core/shared setting metadata를 코드와 descriptor에 연결하고 CLI에서 고정 service
    이름 도움말 예시를 제거했다. Python/TOML syntax 및 diff 검토만 했으며 config/setup/
    route/post-launch/DB adapter의 runtime 동작과 전체 acceptance pass는 실행하지 않았다.
  - SMTP는 공통 shared 설정 파일과 명시적 `setup mail` 명령만 있었고, 서비스 첫 setup이나
    launch가 그 설정을 안내하지 않았다. 서비스 descriptor의 `setup.optional_config`에
    mail 의존을 선언하게 하고 common setup에서 한 번 제안하도록 설계했다. 거절은 private
    shared config에 저장해 매 launch마다 묻지 않으며, SMTP 미설정도 서비스 시작 실패 조건이
    아니다. setup/launch 인터랙션은 아직 실환경에서 검증하지 않았다.
  - 전체 구조 재검토에서는 descriptor의 미지원 키가 일부 위치에서 조용히 무시되거나,
    선언한 capability handler의 누락이 해당 동작 호출 때까지 드러나지 않는 문제가 확인됐다.
    catalog의 nested descriptor 키 검증을 강화하고 launch/setup 상태 변경 전에 handler를
    preflight하도록 보강했다. removal은 Compose 제거와 route 정리 이후 shared database를
    삭제하게 순서를 조정해 중간 실패가 데이터 삭제로 번지는 범위를 줄였다. 이어 shared
    설정 descriptor 위치도 통일해 `MARIADB_CLIENT_VERSION` 선언을 infra descriptor에서
    `config/shared/database.toml`로 옮겼다. 이 TOML이 shared ownership을 선언하고,
    `database.env.default`에는 추적 기본값만 남는다. infra는 MariaDB 서비스와 dependency
    group의 소유자로 유지된다.
    초기에 `tests/test_cli.py`의 구형 Hermes 중앙 함수/help 기대와
    `tests/test_remove.py`의 Hermes 전용 remover 가정이 현재 구현과 어긋난 것을 발견했다.
    테스트를 capability 계약과 공통 descriptor 기반 remover 흐름으로 바꾸고,
    설정 파일은 첫 setup 전에는 없을 수 있다는 점을 반영해 descriptor import 시 실제 env
    파일 존재를 요구하지 않도록 수정했다. 새 clone에서 발생하던 import 실패도 이 과정에서
    확인됐다. Python 3.15에서 전체 36개 테스트가 통과했고, removal Compose 실패 시 route와
    shared database를 보존하는 순서 테스트도 포함했다. 실제 Docker/Cloudflare 환경 동작은
    여기서 검증하지 않았다. shared descriptor 이동 후에도 Python 3.15에서 전체 36개 테스트와
    TOML/catalog 검증을 다시 통과했다.
  - 서비스 추가 규격을 처음 보는 기여자와 AI가 따를 수 있도록
    `docs/adding-services.md`와 `docs/prompts/add-service.md`를 작성했다. Compose와 유효한
    descriptor만 있으면 중앙 CLI 분기 없이 catalog가 검색한다는 점, 공개 Caddy route에는
    gateway snippet이 필요하고 미지원 shared group/capability는 플랫폼 변경이라는 경계를
    명시했다. 실제 신규 서비스를 이 guide/prompt만으로 완성한 기여자 검증은 아직 없다.
  - lifecycle 계약 업데이트는 `codex/service-lifecycle-hooks`와
    `codex/service-lifecycle-messages` feature branch에서 작업 중이다. OpenDock의
    `test_cli.py` 14개, `test_lifecycle_contract.py` 4개, `test_distribution.py` 8개와
    OpenDock-Services의 release pipeline 7개 테스트가 통과했다. n8n-v2/v3 0.1.1 package를
    임시 디렉터리에 빌드해 descriptor validator로 검사했고, Uptime Kuma의 hook 없는
    descriptor와 Mastodon/Supabase `post_start` handler를 확인했다. 사용자가 관찰한 느린
    n8n bootstrap은 실환경에서 발생한 현상이나, 새 안내 메시지는 아직 배포해 확인하지
    않았다. 코드도 아직 commit/push/CI publish되지 않았다.
  - 사용자가 `./opendock setup hermes`에서 기본값에 Enter를 눌렀는데도
    `HERMES_SUBDOMAIN`이 변경된 것으로 표시됐다. 기본값 migration 직후 setup이
    이미 실효값인 tracked default를 private `.env`에 다시 쓰는 경로로 판단해,
    현재 실효값을 그대로 유지한 입력은 저장하지 않도록 수정했다. 수정 후 동작은
    아직 확인되지 않았다.
- 보존할 교훈:
  - 공통 UX와 공통 구현은 같은 뜻이 아니다. 사용자 명령을 통일하면서 서비스별
    운영 지식과 자원 소유권은 해당 서비스 가까이에 둘 수 있다.
  - 한 명령의 예외 처리를 분리하기 전에 전체 command family를 대상으로 경계를
    잡아야 중앙 dispatcher의 조건문을 다른 명령으로 옮기는 일을 피할 수 있다.
  - capability를 선언형 metadata와 optional procedure로 구분하면 단순 서비스에
    빈 hook을 강요하지 않으면서 복잡한 서비스의 동작을 명시할 수 있다.
- 참고: [Terraform plugin architecture](https://developer.hashicorp.com/terraform/plugin/how-terraform-works),
  [Ansible Collections](https://docs.ansible.com/collections.html),
  [Python plugin discovery](https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/).
- 검증 상태: 사용자가 help/list, Hermes launch, Hermes setup 및 기존 onboarding
  skip을 실제 환경에서 확인했다. setup migration marker 수정도 사용자가 원격 개발
  환경에서 `sync` 후 Mastodon setup을 다시 실행해 반복 메시지가 해결된 것을
  확인했다. secret generation·service validation, Supabase prepare, 선언형 Hermes
  removal, service command help metadata, 설정 migration 일반화는 코드에 반영됐지만
  실환경에서는 확인되지 않았다. 자동화 테스트,
  깨끗한 데이터의 첫 onboarding, 모든 서비스 removal 후의 깨끗한 환경 전체 실행,
    Linux/macOS 양쪽 동작도 미검증이다. 이번 infra descriptor 이동은 정적
    구문/차이 검토까지만 했으며 setup/secrets 실행과 설정 migration 영향은
    아직 검증하지 않았다. 이후 lifecycle hook 후속 작업은 로컬 unit test와 n8n package
    build/descriptor validation까지 통과했지만, 실제 dev package publish 및 새 안내 문구의
    사용자 환경 확인은 남아 있다.

## OD-018. 여러 사용자가 쓸 Notion 대안을 홈서버에 고르기

- 상태: `seed`
- 관련 작업: `codex/feature/docmost`의 Docmost 서비스 추가; 완료 후 커밋 해시 기록
- 주제: `AppFlowy의 무료 좌석 제한을 확인하고 Docmost를 OpenDock 서비스로 검토하기`
- 독자 질문: Notion 같은 협업 문서 도구를 자체 호스팅하려는 소규모 팀은 기능,
  라이선스, 자원, 운영 복잡도를 어떤 순서로 비교해야 하는가?
- 참고할 사항:
  - 사용자는 홈서버에서 여러 사용자가 쓸 Notion 대안을 찾았다. AppFlowy Self-Hosted
    무료 티어는 instance당 사용자 좌석 1개와 최대 3명의 guest editor를 구분해 제공하므로,
    여러 일반 사용자 계정 요구와 맞지 않는다는 점을 공식 배포 README에서 확인했다.
  - Docmost 공식 문서는 실시간 공동 편집, Spaces, self-host Docker 구성을 설명한다.
    공식 Community/Business 가격표는 Community의 핵심 협업 기능과 Business 전용 기능을
    구분하며 Bases와 Kanban은 Business feature로 나열한다. 따라서 “Notion 대체”라는
    표현만으로 모든 데이터베이스 기능이 무료라고 가정하지 않고 사용 목적과 요금표를
    대조해야 한다.
  - OpenDock 파일럿은 별도 `codex/feature/docmost` branch에서 service descriptor,
    `.env.default`, 기본 hostname `docmost`, PostgreSQL shared-database 초기화,
    shared Redis DB index 1, 선택적 SMTP 연결, Caddy handler, 서비스별 README와
    `knowledge` group으로 구성한다.
    Compose가 제공하는 PostgreSQL/Redis를 중복 기동하지 않고 OpenDock의 공통 infra를
    사용하는 방향이다.
  - 업로드 파일은 Compose named volume에 두고, 제거 계약은 Docmost 전용 shared PostgreSQL
    database/role과 upload volume만 소유한다. 공통 infra volume이나 다른 서비스 상태는
    제거하지 않는다. SMTP가 없더라도 서비스 실행은 허용하되 초대 메일 등은 relay 설정이
    필요하다고 안내한다.
  - 실제 자원 사용량은 서버 사양과 사용자 규모에 따라 달라지며 공식 문서에서 최소 RAM을
    확인하지 못했다. 따라서 저사양 서버에서도 충분하다고 추측하지 않는다.
  - 첫 사용자 실행에서 `docmost/docmost:v0.97.0: not found`가 발생했다. GitHub release
    이름은 `v0.97.0`이지만 Docker Hub의 실제 image tag는 `0.97.0`으로 `v` prefix가 없다.
    `.env.default`를 `0.97.0`으로 수정했고 사용자가 다시 실행해 기동을 확인했다.
    Docker Hub tag 페이지는 linux/amd64와 linux/arm64 manifest를 표시한다.
  - 사용자는 초기 `Create workspace` 화면이 공개 가입인지 질문했다. 공식 설치 안내와
    화면의 동작은 첫 workspace/admin을 생성하는 최초 설정 흐름이며, 이 단계는 가입 확인
    메일을 발송하지 않는다. 사용자는 이후 Forgot password 이메일 발송을 실환경에서
    확인해 OpenDock shared SMTP 설정이 Docmost에 적용됨을 검증했다. 초대 이메일 수신은
    아직 따로 확인하지 않았다.
- 보존할 교훈:
  - SaaS 대안 선정은 화면 기능 비교만이 아니라 무료 계정의 정의(사용자와 게스트),
    라이선스 기능 구분, 데이터 자원 소유권, update/backup 운영모델을 함께 봐야 한다.
  - OpenDock service contribution은 upstream의 Compose를 그대로 복사하는 것보다 공통
    infra 재사용과 삭제 경계를 명확히 하면서 쉬운 launch UX를 보존하는 작업이다.
- 검증 상태: 공식 AppFlowy, Docmost 문서와 Compose 구성을 조사하고 OpenDock service
  파일을 작성했다. 사용자는 Docker image tag 수정 후 launch와 초기 workspace/admin 설정,
  Forgot password 메일 발송을 실환경에서 확인했다. 초대 메일 수신과 실제 다중 사용자 협업은
  아직 별도 검증되지 않았다. 현재 branch에서 catalog discovery, config/Compose rendering,
  route publish, descriptor 기반 removal과 OpenDock command-level setup 동작도 아직 검증하지
  않았다.

## OD-019. 편한 Docker volume과 외장 디스크 선택권을 함께 제공하기

- 상태: `seed`
- 관련 작업: `codex/feature/service-storage-paths`; `AGENTS.md`,
  `scripts/opendock_storage.py`, `scripts/opendock_catalog.py`,
  `scripts/opendock-remove.py`, Jellyfin/Immich descriptor와 Compose 설정
- 주제: `서비스 기본값은 간단하게, 큰 사용자 데이터만 외장 디스크로 보내는 설계`
- 독자 질문: self-hosted Docker 플랫폼에서 named volume의 편리함을 유지하면서
  사진·영상처럼 큰 데이터만 외장 디스크에 두려면 경로 설정과 제거 소유권을 어떻게
  설계해야 할까?
- 참고할 사항:
  - 사용자는 Docker named volume 덕분에 서비스가 기본 설정으로 편하게 동작하는 점을
    좋아했지만, 외장 디스크를 붙였을 때 미디어 서비스 저장 위치를 선택할 수 없다는
    필요를 제기했다. 전역 storage root 하나보다 데이터가 큰 서비스만 각자 경로를 갖는
    방식을 선호했다.
  - 설계는 기존 checkout-local 경로를 계속 기본값으로 두고 서비스별 setup field로
    변경 경로를 받는다. 따라서 미디어가 아닌 서비스에 새로운 storage 질문을 요구하지
    않고, 기존 설정 파일의 경로를 바꾸지 않아 기존 사용자 데이터의 위치도 자동으로
    변경하지 않는다.
  - Jellyfin은 `JELLYFIN_MEDIA_PATH`로 `/media` 소스를 지정한다. Immich는
    `IMMICH_LIBRARY_PATH`로 사진·영상 라이브러리만 지정하고 PostgreSQL 경로는 로컬에
    남긴다. WordPress는 현재 `services/wordpress/data/webroot` 전체를
    `/var/www/html`에 연결하고 제거 계약도 이 경로를 데이터로 소유한다. 따라서 별도
    uploads-only 구조를 새로 만들지 않고 `WORDPRESS_WEBROOT_PATH`로 전체 webroot를
    선택하게 한다. 이미지 문서상 이 webroot에는 WordPress core와 plugins/themes, uploads가
    함께 들어간다.
  - Hermes는 이번 공통 path 설정에서 제외한다. upstream Docker 안내는 `/opt/data`에
    설정, API key, 세션, 스킬, 메모리 등 모든 app state를 저장한다. OpenDock에서는 이
    state가 named volume이며, 별도 sandbox directory는 Hermes 컨테이너와 Docker host에서
    같은 absolute path여야 하고 orphan sandbox container cleanup도 이 경로를 이용한다.
    따라서 단순 media path와 같은 UX로 바꾸지 않고 별도 storage/security 설계를 남긴다.
  - 서비스 descriptor가 mount target과 접근 유형을 선언하고, Compose는
    `create_host_path: false`를 사용한다. 빠진 checkout-local 기본 경로는 OpenDock이
    launch/up에서 만들지만, 사용자가 지정한 사용자 경로는 자동 생성하지 않고 존재와
    접근성을 확인한다.
  - tracked `.env.default`에 안전한 경로가 있으면 설정 검증은 그 기본값만으로 통과할 수
    있다. 그래서 launch가 첫 선택을 묻지 않고 곧바로 기본 경로를 쓸 수 있다는 UX 결함을
    확인했다. storage 경로 선택은 첫 launch에서 한 번 물어보고, 기본값을 선택해도
    서비스 비공개 `.env`에 선택 사실을 기록해 반복 launch에서는 재질문하지 않도록 한다.
    `remove`가 서비스 설정을 지운 뒤 다시 launch하면 경로 선택도 다시 받는다.
  - 공통 설정 검증은 지정한 경로의 존재, 디렉터리 여부, 접근 권한을 확인한다. 경로를
    사용자가 정한 대로 쓰며 외장 디스크 여부를 판정하지 않는다. Compose의
    `create_host_path: false`는 경로 자체가 없을 때 자동 생성하지 않지만, 디스크가 빠져도
    그 mount-point 디렉터리가 시스템 디스크에 남아 있으면 이를 구별하지 못한다.
  - `remove`는 설정된 외부 경로를 전체 제거 계획에 정확히 보여주고 확인 후 삭제하도록
    설계했다. mount root, 사용자 home, symlink 경로와 다른 서비스의 storage path와
    겹치는 경로는 거부한다. 이 경계는 실제 외장 디스크에서 반드시 검증해야 한다.
  - 경로 설정 변경은 데이터를 복사하지 않는다. 기존 서비스를 이전할 때는 데이터와
    앱 상태를 백업하고 서비스별 migration 절차를 따라야 한다. 특히 Immich는 파일
    라이브러리와 DB 상태를 함께 고려해야 한다.
- 보존할 교훈:
  - zero-config 기본값과 선택 가능한 고급 경로는 공존할 수 있다. 전역 옵션으로 모든
    서비스의 모델을 바꾸기보다, 큰 사용자 데이터가 있는 서비스만 선언형으로 확장한다.
  - Compose bind mount의 경로가 설정되는 순간 실행뿐 아니라 mount 누락, 이동, 백업,
    완전 제거의 의미도 함께 설계해야 한다.
  - user data 경로를 단순히 삭제 대상으로 간주하지 말고, 기본 경로·외부 경로 모두
    명령의 preview에 드러내며 그 소유 범위를 명시한다.
- 검증 상태: 코드와 문서의 정적 diff 검토 및 `git diff --check`만 수행했다. 자동화
  테스트는 실행하지 않았고, Docker Compose rendering, 기본 경로 자동 준비, 지정 경로 연결,
  Linux와 macOS Docker 환경의 mount 처리, 경로 누락 시 동작, 외장 경로를 포함한 `remove`는
  아직 확인되지 않았다. 사용자의 실제 디스크에서의 검증도 대기 중이다.

## OD-020. OpenDock 서비스 배포를 private ZIP에서 정적 카탈로그로 다시 설계하기

- 상태: `seed`
- 관련 문서: `docs/product-distribution.md`
- 주제: `고객 계정 서버 없이 시작하는 self-hosted 서비스 배포: private ZIP 가설에서 정적 R2 카탈로그로`
- 독자 질문: 공개 플랫폼과 유료 선택 서비스를 분리하고 싶을 때, 구매 권한 서버를
  처음부터 구축하지 않고 고객이 실제로 설치할 수 있는 배포 흐름을 어떻게 시작할까?
- 참고할 사항:
  - 사용자는 OpenDock을 상품화하면서 플랫폼과 선택 서비스를 분리하고, 플랫폼 및
    기본 bundle은 공개 GitHub 저장소, n8n·WordPress·Hermes Agent용 통합 파일은
    별도 프로젝트로 관리하는 방향을 제안했다.
  - 논의에서는 구매 계정이 여러 private GitHub 저장소에 접근하는 방식과 별도
    인증·배포 서버를 두는 방식도 비교했다. 별도 배포 서비스는 장기적인 목표가 될 수
    있지만, 첫 판매를 위해 반드시 먼저 구축해야 하는지는 재검토했다.
  - 초기 가설은 판매처를 특정 플랫폼에 묶지 않고, 판매 채널이 버전이 명시된 서비스
    ZIP을 전달하며 고객이 OpenDock 명령으로 가져오는 구조다. GitHub은 개발 원본을
    관리하고 ZIP은 고객용 배포물이 되는 역할 분리를 둔다.
  - 패키지에는 서비스 descriptor, Compose 및 통합 코드, capability API 호환성,
    릴리스 노트와 무결성 정보가 필요하다고 제안했다. 비밀값, 사용자 데이터,
    `.env`는 패키지에서 제외하고 업데이트가 고객 설정과 데이터를 보존해야 한다.
  - 상세 설계에서는 설치 패키지를 서비스 하나로 제한하고, 확장 코드를
    `extensions/services/<id>/releases/<version>/`에 불변 보관하며 활성 버전은
    로컬 registry로 선택하도록 정리했다. private 설정은 release 디렉터리와 분리해
    `config/extensions/<id>.env`에 두고, 기존/bundled 서비스 ID 덮어쓰기와 임의
    service discovery를 거부한다.
  - ZIP 내부 manifest에 ZIP 전체 해시를 넣으면 자기참조가 생기므로 manifest는
    payload별 크기와 SHA-256을 서명하고, CLI는 전체 ZIP digest를 로컬 등록 정보로
    기록하는 구조로 구체화했다. 서명된 파일 목록을 추출 전에 스트리밍 검증하고,
    stage → immutable release rename → registry 원자 교체 순으로 설치/업데이트한다.
    이전 release와 고객 state를 자동 삭제하지 않는 대신 실패 시 고아 stage/release가
    남을 수 있어 복구 경로가 필요하다.
  - capability 코드는 CLI와 같은 로컬 권한으로 실행되므로 압축 해제 검증은 코드
    샌드박스를 제공하지 않는다는 trust boundary를 명시했다. 서명 형식과 검증 라이브러리,
    신뢰 키 배포·회전, 실제 파일 형식은 아직 결정/구현되지 않았다.
  - 저장소 경계는 독립된 `OpenDock`과 `OpenDock-Services`로 두고 submodule은
    사용하지 않는 방향으로 구체화했다. 플랫폼은 공통 CLI와 baseline bundle 및 package
    lifecycle을, 서비스 repo는 선택 통합의 canonical source와 ZIP 릴리스를 소유한다.
    n8n·WordPress·Hermes는 문서에 나온 초기 후보일 뿐, 유료/core 구분과 이관 순서는
    아직 확정되지 않았다. 패키지 설치 경로가 준비되기 전까지 bundled 구현을 삭제하지
    않는 단계적 이관 원칙을 기록했다.
  - 현재 descriptor/Compose 구성을 비교해 n8n을 파일럿 후보로 추천했다. n8n은 단일
    Compose 앱과 named volume, SMTP opt-in, routing 메타데이터로 공통 package lifecycle을
    점검할 수 있고, WordPress의 shared database/custom command 및 Hermes의
    runtime/prepare capability보다 서비스별 migration 변수가 적다. 이는 코드 실행이나
    고객 환경 검증 결과가 아니라 저장소 구현을 기준으로 한 설계 판단이다.
  - 사용자는 `services/extensions/`와 `services/bundles/`로 분류하는 구조를 제안했고,
    이를 채택하는 방향으로 설계 문서를 갱신했다. OpenDock-Services에는 추적된 서비스
    파일만 `services/extensions/{n8n,wordpress,hermes}/`로 복사했으며, 로컬 `.env`는
    복사 대상에서 제외했다. OpenDock의 기존 서비스 경로/실행 코드는 아직 이전하지
    않았으므로 설치 경로와 catalog/config migration은 구현 단계에서 함께 처리해야 한다.
  - WordPress multisite helper가 `scripts/wp-multisite.py`에 있어 서비스 ZIP만으로
    명령이 완결되지 않는 점을 확인했다. helper를 서비스 `commands/` 아래로 옮기고
    공통 dispatcher가 `OPENDOCK_SERVICE_DIR`을 전달하도록 바꾸는 로컬 코드 변경을 했다.
    이 경로 변경은 테스트하지 않았다.
  - 확장 후보 10개의 service-owned tracked files와 Caddy handler snippets를
    OpenDock-Services에 복사했다. 초기 파일 이관에서 `gateway/caddy/conf.d/*.caddy`가
    Compose/service 디렉터리 바깥에 있어 패키지 ZIP에는 routing 파일을 명시적으로
    포함해야 한다는 누락을 확인했다. 상세 설계는 active release의 routing handler만
    import하고 uninstalled source나 이전 release는 경로 게시에 사용하지 않도록 했다.
  - 사용자는 OpenDock 번들을 Homepage와 Uptime Kuma로 한정하고 Nextcloud도 확장으로
    두는 안을 선택했다. Nextcloud는 일반 사용자 가치가 높지만 shared database와 데이터
    관리를 baseline에서 분리해 기본 footprint를 작게 가져가는 판단이다.
  - 이 선택에 따라 Homepage와 Uptime Kuma의 추적 디렉터리와 private `.env`를
    `services/bundles/`로 이동했다. 기존 `.env` 두 개는 값 출력 없이 0600 제한 백업을
    만든 뒤 같은 파일로 함께 이동했다. catalog discovery, Compose/config/remove 경로를
    descriptor에서 해석하도록 바꾸고 flat legacy 디렉터리도 이관 중 임시로 인식하게 했다.
    코드 경로 실행과 실제 launch/remove는 아직 테스트하지 않았다.
  - extension 설치 경로를 repository 아래에 둘 경우 원격 `sync`의 destination-prune가
    registry와 package releases를 지울 수 있음을 발견해 `services/extensions/`를 sync
    제외 및 prune 보호 대상으로 추가했다. 서비스 수명주기 분리만으로는 운영용 sync가
    보존 경계를 자동으로 알지 못한다.
  - 이후 사용자는 기존 extension 디렉터리를 새 core discovery에서 제외하고 로컬
    `archive/`에 임시 보존해 새 구조를 독립적으로 검증하기로 했다. 10개 서비스 트리와
    10개 Caddy snippet을 이동했으며 archive는 Gitignore, catalog, sync/prune에서
    제외된다. private 설정과 사용자 데이터는 삭제하지 않았다. 새 core catalog는
    `services/bundles/*/compose.yml`만 찾는다.
  - 사용자는 `install → setup → launch`로 패키지 흐름을 검증하려 한다. `setup` 없이
    `launch`해도 공통 설정부터 확인해야 한다는 UX에 합의했다. launch의 설정 확인이
    prepare capability 유무에 묶여 있던 코드를 고쳐, 모든 선택 서비스가 설정 확인을
    거친 뒤 필요한 준비 훅으로 진행하게 했다. CLI 설치 명령과 실제 package install은
    아직 남아 있다.
  - 이후 제품 방향을 원점에서 재검토했다. paid/free 분류와 entitlement를 초기 범위에서
    제외하고, 플랫폼 배포에 서비스 bundle을 포함하지 않으며, 모든 앱을 동일한
    catalog service로 취급하기로 했다. 따라서 앞서 제안한 bundle/extension 분류와
    유료 ZIP 판매 흐름은 현재 설계의 기준이 아니다.
  - 별도 Worker/API 대신 정적 JSON 카탈로그를 R2에서 제공하고, CI만 private
    OpenDock-Services와 R2 write 권한을 갖는 흐름을 합의했다. CLI는 카탈로그를
    내려받아 로컬 검색하고, 패키지 SHA-256을 카탈로그 값과 비교한다. 서명은 키 운영
    복잡도 때문에 우선 미루되 catalog와 package를 함께 바꿀 수 있는 공격자에 대해서는
    게시자 진위 보장을 제공하지 않는다는 한계를 기록했다.
  - 패키지와 실행 인스턴스를 분리한다. WordPress package 하나를 설치한 뒤 A 도메인과
    B 도메인에 별도의 설정·컨테이너·데이터를 갖는 인스턴스를 운영하며, 모든 지원
    서비스가 같은 모델을 사용할 수 있어야 한다. Linux 우선, macOS 다음, WSL2 이후로
    OS 지원 순서도 정했다.
  - 기존 `scripts/opendock_capabilities.py`의 runtime environment, secret plan/generate,
    config validation, prepare 사례와 `post_launch` 흐름을 확인했다. 새 API v1 초안은
    필요한 동작을 보존하되 setup/readiness/upgrade/purge 계약을 추가하고, 함수 시그니처와
    컨텍스트를 새로 정의한다. descriptor가 setup hook과 필요한 infra adapter를 명시할
    때만 setup/launch가 실제 공유 인프라에 접근한다.
  - 도메인은 서비스 하나가 소유하는 값이 아니라 플랫폼이 등록하는 공용 base domain으로
    모델링했다. 한 도메인에 서로 다른 서비스 인스턴스가 붙을 수 있고, 라우트 hostname은
    충돌을 검사한다. v1에서는 `(service_id, domain)`마다 인스턴스 하나를 두며, CLI의
    `--domain`은 이 쌍으로 인스턴스를 선택한다.
  - 새 설계 문서는 `docs/product-distribution.md`,
    `docs/catalog-and-package-contract.md`, `docs/service-contract.md`,
    `docs/command-model.md`에 기록했다. 기존 코드는 호환성 기준이 아니라 참고 자료로
    취급하고, 이전 branch 변경을 새 방향과 충돌하는 부분, 재사용할 개념, archive
    보존물로 분류했다.
  - 후속 steering에서 사용자는 bundle을 완전히 없애고 모든 앱을 OpenDock-Services에서
    별도 패키지로 설치하는 방향을 확정했다. 첫 수직 파일럿은 Homepage가 아니라 Uptime
    Kuma로 정정했고, CI tag/수동 release가 dev R2에 ZIP과 정적 catalog를 게시하는
    경로를 준비했다. 일반 Git push만으로 모든 변경을 자동 배포하지 않고 명시적인
    release version을 사용한다.
  - OpenDock에 `update`, `search`, `install` CLI와 `scripts/opendock_distribution.py`를
    추가했다. catalog schema/ID/version/key/digest/크기를 검증하고, ZIP 전체 SHA-256을
    검사한 다음 경로 traversal, 중복 ZIP entry, symlink를 거부하고 staging에서
    `services/extensions/<id>/releases/<version>`로 활성화한다. 로컬 설치 registry는
    서명 키 ID를 요구하지 않는다. 실행 코드 import 없이 descriptor를 읽어 설치를
    등록한다.
  - 첫 임시 설치 통합 검증은 registry release 경로 prefix 비교 버그를 찾아냈다.
    비교 길이를 경로 구성요소 수에 맞춘 뒤, 가짜 다운로드 응답을 사용해 package
    install부터 `ServiceCatalog` discovery까지 성공했다. 이는 실제 R2 또는 Docker
    환경 검증과 구분해야 한다.
  - OpenDock-Services에 Uptime Kuma 원본, 자체 routing handler, deterministic ZIP
    builder, catalog 갱신 스크립트, dev 전용 GitHub Actions workflow를 추가했다. 로컬에서
    ZIP을 만들고 생성 catalog를 OpenDock validator로 검사한 뒤 `uptime-kuma/v0.1.0`을
    tag push했다. GitHub Actions run `42201031065`가 package upload와 catalog-last 게시를
    성공으로 완료했다.
  - 공개 catalog URL도 반복해서 shell에 export하지 않도록 core 설정 소유권에 등록하고,
    사용자가 `dev` 선택을 매번 기억하지 않아도 되도록 개발용 `dev_opendock` wrapper가
    distribution 명령에 `--environment dev`를 고정해서 붙이게 했다. 운영 URL은 core 설정
    파일에서 별도로 선택한다. R2 공개 URL은 이 문서에 기록하지 않는다. 사용자가 실제
    OpenDock checkout에서 `./dev_opendock update`를 실행해 1개 서비스 catalog를 캐시했고,
    `search uptime`에서 Uptime Kuma `0.1.0`을 찾은 뒤 `install uptime-kuma`로
    `services/extensions/uptime-kuma/releases/0.1.0`에 설치했다. 이로써 dev R2 fetch와
    package install은 사용자 환경에서 확인됐다. Package setup, launch, purge 및
    domain별 instance 동작은 아직 검증하지 않았다.
  - 이후 OpenDock checkout에서 Uptime Kuma release가 서비스 catalog와 설정 경로에
    연결되는지 확인했다. `./opendock list services`에서 발견되고
    `./opendock check-config uptime-kuma`가 `OK`를 반환했다.
    `./opendock setup uptime-kuma`는 descriptor의 기본 subdomain 설정을 읽어 완료됐으며,
    기존 설정과 기본값만 사용해 별도 애플리케이션 인프라를 시작하지 않았다. Registry의
    서비스 ID, release 경로 버전, descriptor 버전이 불일치하지 않도록 catalog 검증도
    강화했다. 다음 단계에서 package launch를 기존 공통 lifecycle에 연결하고,
    `docker compose up --wait --wait-timeout 180`으로 서비스 및 의존 infra의 실행 상태를
    확인하도록 했다. Cloudflare 설정이 없을 때에는 local route는 있지만 DNS/Tunnel은
    변경하지 않았다는 partial 상태를 분명히 출력한다. `docker compose config`와 설정
    검증은 통과했지만 Docker daemon이 실행되지 않아 실제 컨테이너 launch는 검증하지
    못했다. Uptime Kuma descriptor에는 Compose healthcheck/readiness hook이 없어 Compose의
    실행 확인이 HTTP UI 준비까지 의미하지 않는다는 한계도 확인했다.
  - 사용자가 `./dev_opendock launch uptime-kuma`를 실행하자 선언된 `infra` dependency가
    `Unknown service: infra`로 실패했다. 추적 결과 Compose 인자 구성 자체가 아니라
    settings의 `compose_env_files()`가 platform component도 service package로 조회하는
    소유권 혼동이었다. platform descriptor에 등록된 component를 service catalog와
    구분해 config/env 파일을 구성하도록 수정했고 `infra`, `gateway`, Uptime Kuma의
    Compose config 렌더 및 infra config 검증을 통과했다. Docker daemon 실기동은 별도다.
  - 이후 launch 로그에서 Uptime Kuma와 infra는 정상인데 Caddy가 반복 재시작하는 것을
    확인했다. Caddy 로그는 extension routing 파일의 `(uptime_kuma_proxy)` 선언을
    host site 블록 안에서 import해 `unrecognized directive`로 처리했다. 패키지 routing
    파일은 Caddyfile 최상위에서 먼저 import하고, 생성 host route는 snippet 이름만
    import하도록 renderer를 수정했다. 서비스별 legacy Caddy snippet도 platform에서
    제거해 package handler와 중복되지 않게 했다. 이 수정은 로컬 renderer/config 검사까지
    확인했으며 실제 Caddy reload는 사용자의 Linux 환경에서 재검증해야 한다.
  - Caddy 문법 문제 수정 뒤 로그에서는 hostname 인증서 발급이 `tls-alpn-01` challenge로
    실패했다. 기본 배포는 Cloudflare가 TLS를 종료하고 Tunnel이 Caddy의 HTTP origin으로
    연결하는데, renderer가 `https://` site block도 만들어 Caddy에 별도 Let's Encrypt
    인증서를 요청시킨 것이 원인이었다. 기본 Tunnel 라우트를 HTTP-only로 생성하고 직접
    Caddy TLS는 별도 exposure mode가 필요하다고 문서화했다. 이후 사용자가 실제
    Linux에서 Caddy origin의 `/`가 Uptime Kuma의 `/setup-database`로 302 redirect하고,
    setup 정보와 JS/CSS asset이 정상 응답하는 것을 확인했다. 그런데 공개 HTTPS에서는
    document와 JS가 빈 200 응답으로 보여 Safari·Chrome·Firefox 모두 빈 화면이었다.
    Minibuntu에는 cloudflared 프로세스, systemd service, Docker container가 없었고,
    실제 Tunnel connector는 notebuntu에 있었다. Connector가 있는 notebuntu에서
    Minibuntu Caddy로 도달하도록 Tunnel origin을 바로잡자 화면이 표시됐다. 따라서 이
    증상은 Uptime Kuma frontend나 browser보다 Cloudflare Tunnel의 origin 경로 문제였다.
  - 이 운영 경험을 바탕으로 Cloudflare를 선택 사항으로 두면 local launch는 성공하지만
    외부 공개는 되지 않는 상태가 생겨 초보 사용자가 혼란스러울 수 있다는 결론을 냈다.
    `OPENDOCK_CLOUDFLARE_SETUP_SKIPPED`와 선택 설정 문구를 제거하고, 첫 system setup과
    public launch 전에 Cloudflare 설정을 필수 검증하는 방향으로 바꿨다. `launch infra`는
    내부 구성만 올리는 명령이라 예외다. API 설정이 있어도 별도 connector 실행과 origin
    도달성은 보장되지 않으므로 사용자 가이드에서 이를 별도 전제 조건으로 설명한다.
  - 후속 코드 리뷰에서 사용자는 Uptime Kuma의 DB/schema/user 자동 생성이 필요하지 않다고
    바로잡았다. Kuma는 SQLite, embedded MariaDB, 외부 MariaDB/MySQL 중 앱 첫 실행에서
    선택하므로 OpenDock은 공유 infra/network만 준비하고 DB 선택과 초기 설정은 사용자에게
    남긴다. 문서에서도 “launch 완료”와 “앱 wizard/readiness 완료”를 구분했다.
  - 같은 리뷰에서 installer가 package digest 외에 catalog의 host/API/schema 호환 범위와
    descriptor 전체를 activation 전에 확인하지 않는 점을 보완했다. OpenDock 자체 버전
    source는 아직 없으므로 그 compatibility range는 형식만 검사하고 실행 적용은 보류했다.
    Registry를 먼저 읽고 검증한 뒤 stage release와 registry를 순서대로 활성화하며 registry
    교체 실패 시 새 release를 롤백하도록 했다.
  - 기존 `domains.conf`가 있을 때 `launch all`에서 빠진 서비스 기본 route를 한 번에 검증해
    추가하도록 했고, setup/preparation 취소 전에 route가 저장되지 않도록 호출 순서를 조정했다.
    Cloudflare publish는 설정된 origin을 기준으로 managed hostname 규칙을
    갱신한다. 사용자의 별도 Tunnel connector 구성을 자동으로 추론하거나 보존하는 기능은
    넣지 않았다. 알려진 DNS 충돌은 Tunnel 설정 변경 전에 확인한다.
- 보존할 교훈:
  - 개발 저장소 접근 제어와 제품 entitlement는 같은 문제로 취급하지 않는다.
    소스 저장소를 private으로 만드는 것만으로 고객 설치·업데이트 경험이 완성되지 않는다.
  - 판매 검증을 시작하기 전에 인증 서버를 구축할 필요가 있는지, 실제 운영 부담이
    생길 때 자동화해도 되는지 구분한다.
  - ZIP 배포는 가벼운 첫 경로지만 버전 호환, 안전한 압축 해제, 업데이트 시 local
    state 보존, 환불 이후 재다운로드 정책을 명시해야 한다.
- 검증 상태: 설계 문서, catalog client의 local unit test, ZIP/package build,
  generated catalog validation, temporary-root install/service discovery, 실제 tag-triggered
  GitHub Actions dev R2 게시, 사용자가 수행한 `update → search → install`을 확인했다.
  이어서 현재 checkout에서 `list → check-config → setup`을 로컬 확인했다. Setup은
  기본값 경로까지이며 app runtime을 시작하지 않았다. 이후 사용자가 Minibuntu에서 infra와
  Uptime Kuma container가 healthy인 것, Tunnel origin 수정 뒤 외부 HTTPS로 DB first-run
  화면을 여는 것을 확인했다. DB wizard 완료와 post-setup app readiness/purge,
  domain별 instance lifecycle, 깨끗한 호스트, production publish, macOS 호스트 bootstrap 및
  WSL2 지원은 검증되지 않았다. 이번 후속 개선은 Python 정적 컴파일과 diff whitespace
  검토만 했으며 실 Cloudflare/API, package 재설치, `launch all` route migration은 실행하지
  않았다. 현재 구현은 catalog의 `supported_hosts` 값을 구조적으로 검증하지만, 그 값으로
  현재 호스트의 설치 가능 여부를 차단하지 않는다. Uptime Kuma의 macOS 지원 여부는 공식
  자료를 확인하지 않았으므로 미확정이며, 이 기록은 지원 제한으로 해석하면 안 된다.

## OD-021. n8n 3.x early access를 기본 self-hosted 서비스에 바로 채택하지 않기

- 상태: `seed`
- 관련 문서: `OpenDock-Services/services/extensions/n8n-v2/README.md`,
  `OpenDock-Services/services/extensions/n8n-v2/.env.default`,
  `OpenDock-Services/services/extensions/n8n-v3/README.md`
- 주제: `새 메이저 버전보다 안정 채널과 데이터 migration 경계를 먼저 확인하기`
- 독자 질문: 새 메이저 버전이 공개됐을 때 self-hosted 기본 이미지를 즉시 올릴지,
  별도 서비스 ID로 분리할지 어떤 근거로 결정할까?
- 참고할 사항:
  - 이 작업 중 사용자가 n8n 3.x 채택과 2.x/3.x 별도 service를 제안했다. 공식
    release/docs를 확인한 시점에 3.0은 early access로 표기됐고, 안정 release 목록은
    2.46.6까지 확인됐다.
  - 공식 3.0 breaking changes 문서는 migration report 사용을 권하고, 여러 legacy node
    제거, binary storage 경로 변경, 보안/config 기본값 변화 등을 기록한다. 서비스는
    workflows, credentials, encryption key를 named volume과 private config에 보관하므로,
    일반 launch에서 기존 volume을 새 major에 넘기는 것은 데이터/동작 영향이 있다.
  - 구현 판단은 stable `n8n` package를 2.46.6으로 고정하고, 3.x를 별도 service ID로
    복제하지 않는 것이다. 하지만 사용자는 두 major를 분리 실행하는 방향을 선택해 stable
    `n8n-v2`와 early access `n8n-v3`로 나눴다. 둘은 각각 `n8n-v2`/`n8n-v3`
    hostname, package ID,
    container, named volume, encryption key를 사용한다. 별도 ID는 단순 version alias가 아니라
    독립 데이터 경계를 제공한다.
  - 근거: 공식 `v30-breaking-changes.md`, official release notes, n8n Docker image tags;
    `OpenDock-Services/services/extensions/n8n-v2/.env.default`와
    `OpenDock-Services/services/extensions/n8n-v3/.env.default`의 image pin 및 README 경고.
  - 검증 구분: 공식 페이지에서 early-access status와 migration scope를 확인했다. 실제 n8n
    2.x/3.x 컨테이너, workflow migration, restore/rollback은 아직 검증되지 않았다.
  - 글에서는 “새 major를 피해야 한다”는 일반 규칙으로 단순화하지 말고, 릴리스 채널,
    service data ownership, migration tooling, rollback 가능성을 확인해 기본값과 실험 경로를
    나누는 판단 과정을 보존한다.

## OD-022. bootstrap이 개발 저장소 전체를 설치해야 할까

- 상태: `seed`
- 관련 파일: `scripts/bootstrap.sh`, `scripts/run-cloudflared.py`,
  `config/shared/cloudflare.toml`, `config/cloudflare.env.default`, `README.md`
- 주제: `Git 없이 시작하는 최소 설치: 저장소 checkout과 사용자 runtime을 분리하기`
- 독자 질문: 새 Linux/macOS 서버에 GitHub 프로젝트 전체를 복제하지 않고
  실제 실행에 필요한 파일만 안전하게 설치하려면 무엇을 기준으로 삼아야 할까?
- 참고할 사항:
  - 사용자가 bootstrap 결과 경로에 `.git`, `.github` 등 개발 파일이 모두 있는 것을
    발견했다. 이전 bootstrap은 `git clone` 자체를 설치 방식으로 삼아서 Git도 필수였고,
    사용자 runtime과 private 개발 저장소 checkout의 경계가 없었다.
  - 현재 OpenDock CLI는 `opendock`, `pyproject.toml`, `scripts/` 런타임 모듈,
    config descriptor/default, infra/gateway Compose와 descriptor, Caddy 기본 설정,
    DB adapter, static root marker만 필요하다. 별도 서비스 코드는 설치 시 static catalog에서
    받으므로 private OpenDock-Services tree를 bootstrap에 포함할 이유가 없다.
  - bootstrap은 GitHub branch source archive를 curl로 받고 Python tar reader로 안전한
    allowlist만 staging directory에 푼 뒤, 완성된 minimal runtime directory를 설치 경로로
    이동한다. `.git`, `.github`, tests, docs, legacy bundled service trees를 사용자 경로에
    복사하지 않는다. Ubuntu에서도 Git을 설치하지 않는다.
  - 설치 방식 결정은 archive 전체를 네트워크에서 다운로드하되 target에는 필요한 파일만
    기록하는 것이다. 현재 구현은 임시 tarball bandwidth를 줄이지는 않지만 Git metadata와
    개발 자산을 사용자의 persistent install root에 남기지 않는다.
  - 기존 `config/cloudflare.env`를 유일한 credential source로 두고 connector용 token-only
    파일은 cloudflared 실행 중 권한이 제한된 임시 파일로만 만든다. cloudflared가 dotenv를
    직접 읽지 못하는 인터페이스를 따라가되 token을 process argv 또는 영구 중복 파일에
    넣지 않는다. 기존 cloudflared 프로세스가 발견되면 bootstrap이 종료하는 대신 그대로
    두고 안내를 출력한다.
  - macOS에서 Homebrew가 설치한 `cloudflared 2026.10.7`이 `--token-file` 미지원으로
    오인됐다. 실제 도움말에는 flag가 있었고, `set -o pipefail` 아래의 `grep -q`가 먼저
    닫힌 pipe 때문에 SIGPIPE를 내며 검사만 실패했다. 전체 도움말을 변수에 받은 뒤
    문자열을 검사하도록 바꿨다.
- 보존할 교훈:
  - clone 가능한 개발 저장소가 곧 제품 설치 artifact인 것은 아니다. 새 호스트에 필요한
    runtime dependency를 확인하고, source tree와 user-owned config/state를 따로 배포한다.
  - allowlist installer는 우연히 포함된 CI·테스트 파일을 줄이지만, 새 runtime dependency가
    생길 때 allowlist와 clean-root smoke check도 같이 갱신해야 한다.
  - “최소 설치”는 내려받는 바이트 수, 설치 경로에 남는 파일, 필수 host dependency를
    구분해서 설명해야 한다. 이 구현은 Git과 개발 파일을 제거하지만 source archive 전체를
    일시 다운로드한다.
- 검증 상태: 현재 worktree의 allowlist로 만든 임시 minimal root에서 `./opendock help`를
  실행했고 `.git`, `.github`, tests, docs 부재를 확인했다. synthetic archive selection,
  bootstrap Bash syntax/help, Cloudflare setting metadata, runtime token temporary-file cleanup,
  `git diff --check`를 확인했다. 추가로 사용자가 겪은 macOS Homebrew 설치 후 지원 검사
  오류를 재현해, 설치된 `cloudflared 2026.10.7`의 실제 help와 수정된 Bash 검사를 확인했다.
  Tunnel connector의 실제 시작 및 기존 cloudflared daemon과의 실환경 상호작용은 검증하지
  않았다. 깨끗한 Ubuntu/macOS bootstrap 전체 실행과 실제 codeload 다운로드도 아직 검증하지
  않았다.
