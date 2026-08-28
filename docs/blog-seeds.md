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

## OD-008. 서비스가 늘어도 Makefile을 예외 처리로 채우지 않은 확장 구조

- 상태: `seed`
- 관련 이력: `d963f76`, `63437c8`, `d5e6996`, `ca6daef`
- 주제: `service discovery, group, action, hook으로 홈서버 CLI 확장하기`
- 독자 질문: 서로 다른 서비스의 편의 기능을 공통 CLI에 추가하면서 어떻게
  거대한 조건문과 top-level 명령 증가를 피할 수 있는가?
- 참고할 사항:
  - `services/*/compose.yml`을 runtime에 발견하므로 새 서비스 추가에 Makefile
    목록 수정이 필요 없다. `services`, `all`, 단일 service라는 공통 target
    모델 위에 `media`, `communication`, `backend` 같은 목적별 group을
    `services/groups.conf`의 데이터로 추가했다.
  - WordPress multisite 같은 수동·파괴 가능 작업을 top-level
    `make wp-multisite`로 계속 늘리는 대신 `make action <service> <action>`
    dispatcher를 만들었다. action은 service directory가 소유하고, 실행 전
    목록을 발견할 수 있다. 기존 명령은 deprecated shim으로 남겼다.
  - 자동 기동 뒤에만 필요한 Mastodon owner 생성이나 Supabase smoke test는
    `opendock-post-launch.py` hook으로 서비스에 귀속했다. 공통 launch는 hook의
    존재만 확인하며 서비스 세부 지식을 갖지 않는다.
  - 기능이 늘며 `make help`가 명령 이름 나열만으로는 부족해졌다. `launch`와
    `up`, `restart`, `services/all/group`, action의 차이를 사용 시점 중심으로
    재구성했다. 읽기 전용 `make ps`, `make config`는 target 생략 시 `all`로
    동작하게 해 단순 누락을 Make error로 만들지 않았다.
- 보존할 교훈:
  - 공통 workflow는 mechanism을, service directory는 policy와 특수 동작을
    소유하게 하면 서비스 수가 늘어도 중심부가 안정적이다.
  - CLI help도 기능이며 실제 기본값과 오류 동작까지 맞아야 한다.
- 검증 상태: service/group resolution, action discovery, post-launch hook과
  개선된 help 출력은 현재 공통 명령 구조에 반영되어 있다.

## OD-009. 되돌릴 수 없는 WordPress Multisite 전환을 action으로 감싼 이유

- 상태: `seed`
- 관련 이력: `13616b7`, `df1b323`, `63437c8`
- 주제: `자동화할수록 더 신중해야 하는 WordPress Multisite 변환`
- 독자 질문: DB와 설정 파일을 함께 바꾸는 위험한 작업을 어떻게 자동화해야
  편리함이 데이터 손실 위험으로 바뀌지 않는가?
- 참고할 사항:
  - subdirectory multisite 전환은 단순 flag가 아니다. WordPress DB 상태,
    `wp-config.php`, Apache `.htaccess`, container의 실제 webroot가 함께 맞아야
    하며 콘텐츠 생성 뒤 single-site 복귀는 별도 migration이 된다.
  - action은 실행 전 경고와 확인을 요구하고, `YES=1`은 의도적인 자동화에서만
    확인을 생략한다. 변경 전에 WordPress DB dump와 `wp-config.php`,
    `.htaccess`를 timestamp backup한다.
  - host에 WP-CLI를 설치하도록 요구하지 않고 WordPress CLI image를 사용했다.
    변환 뒤 container 환경에 맞는 Apache rewrite rule을 적용하고 서비스를
    restart한다.
  - Cloudflare Tunnel 뒤 HTTPS 인식 문제는 multisite URL 생성과 관리 기능에도
    영향을 줄 수 있어 proxy scheme 수정이 별도의 후속 작업으로 필요했다.
  - 범용 CLI 관점에서는 이 기능이 service-specific action dispatcher를 만든
    계기가 되었다. 위험한 동작일수록 공통 명령처럼 보이지 않고 명시적 service
    namespace 안에 있어야 한다.
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
  - 테스트 서버 반복 배포를 위해 `.sync.env`에 remote, path, SSH port를 두고
    `make sync-dry-run <name>`과 `make sync <name>`을 제공했다. 실제 동기화 전에
    `--dry-run`을 별도 명령으로 눈에 띄게 만든 것이 핵심 안전장치다.
  - rsync는 `--delete`를 사용하므로 source에 없는 파일을 제거할 수 있다.
    그래서 `.git`, `common.env`, `cloudflare.env`, `.sync.env`, 모든 service
    data directory와 backup을 명시적으로 제외한다. Supabase 도입 뒤에는
    `functions.env`도 제외하고 `functions.env.example`만 전달하도록 규칙을
    확장했다.
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
- 검증 상태: dry-run/apply 명령과 제외 정책이 구현되어 있으며 Supabase
  Functions Secret example 포함·실파일 제외를 필터 테스트로 확인했다.
