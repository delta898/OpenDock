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
- 검증 상태: service/group resolution, service-command discovery,
  post-launch hook과 개선된 help 출력은 구현 중이다. 새 dispatcher를 실행해
  확인하기 전까지 검증 완료로 쓰지 않는다.

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
  `scripts/opendock-domains.py`, `scripts/publish-cloudflare.py`,
  `gateway/caddy/conf.d/`, `static-sites/`
- 주제: `특정 정적 사이트 도구에 묶이지 않는 도메인 라우팅 설계`
- 독자 질문: 한 서버에서 Docker 앱과 정적 파일 사이트를 여러 도메인으로
  연결하면서 도메인·실행 방식·Gateway 설정을 어떻게 분리할 수 있는가?
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
  로컬 runtime 및 실제 Cloudflare zone/Tunnel 경로는 아직 검증되지 않았다.

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
    제거를 원했고, 기본 `remove <service>`를 전체 제거로 해석하되 확인을
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
