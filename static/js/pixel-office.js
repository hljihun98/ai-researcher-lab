/*
 * pixel-office.js — 캔버스 기반 픽셀 오피스 렌더러
 *
 * VS Code 확장 "Pixel Agents"(pablodelucca/pixel-agents, MIT) 느낌의 2D 연구소.
 * 엔진 코드는 본 프로젝트에서 자체 작성했다(원 저장소 코드 복붙 없음).
 * 에셋(캐릭터/가구/바닥 PNG)만 재사용한다 — static/assets/ 참고.
 *
 * 특징:
 *  - HTML5 Canvas, 논리 해상도 512×320, CSS 정수배 확대, 픽셀퍼펙트.
 *  - TILE=16 그리드(32×20), 절차적 벽, 가구 스프라이트, BFS 경로탐색.
 *  - 캐릭터 상태머신: idle / walk / sit / type / read / talk / wait.
 *  - 각 에이전트는 자기 자리(seat)를 가지고 평소엔 앉아 있다가,
 *    인카운터가 들어오면 그 장소로 걸어가 마주보고 대화한 뒤 자리로 복귀.
 *  - 말풍선은 캔버스 위 절대배치 <div> 오버레이(Galmuri 픽셀폰트).
 *
 * 백엔드/스키마는 건드리지 않는다. server.py의 reveal()이 아래 공개 API를 호출한다.
 */
(function () {
  "use strict";

  // ---- 상수 ----
  var TILE = 16;              // 타일 한 변(px, 네이티브)
  var GW = 32, GH = 20;       // 그리드 가로/세로(타일)
  var VW = GW * TILE;         // 논리 해상도 512
  var VH = GH * TILE;         // 논리 해상도 320
  var FRAME_W = 16, FRAME_H = 32;  // 캐릭터 프레임(네이티브)
  var WALK_FRAMES = 7;        // 방향당 걷기 프레임 수
  var ANIM_FPS = 8;           // 스프라이트 프레임 스텝
  var WALK_SPEED = 64;        // 이동 속도(px/초) = 4 타일/초
  var CHAR_COUNT = 6;         // char_0..char_5

  var ASSET = "/static/assets/";

  // 방향: 0=down, 1=up, 2=side(오른쪽; 왼쪽은 flipX)
  var DIR = { DOWN: 0, UP: 1, SIDE: 2 };

  // ---- 스테이션(장소) 정의 ----
  // 각 장소: 가구 스프라이트, 배치 타일(x2면 여러 개), 크기(타일), 서서 상호작용할 타일(stand).
  // 좌표는 [col, row]. 벽=상단 3줄 + 좌우 1줄이므로 내부는 row 3..19, col 1..30.
  var STATIONS = {
    library: {
      sprite: "BOOKSHELF", w: 2, h: 1,
      furni: [[2, 3], [5, 3]],
      stand: [[3, 5], [6, 5]],
    },
    whiteboard: {
      sprite: "WHITEBOARD", w: 2, h: 2,
      furni: [[15, 3]],
      stand: [[14, 6], [17, 6]],
      center: [15, 6],   // 파이널 발표 위치
    },
    coffee: {
      sprite: "COFFEE", w: 1, h: 1,
      furni: [[28, 4]],
      stand: [[28, 6], [27, 6]],
    },
    server_room: {
      sprite: "PC", w: 1, h: 2,
      furni: [[2, 10], [4, 10]],
      stand: [[2, 13], [4, 13]],
    },
    meeting_desk: {
      sprite: "DESK", w: 3, h: 2,
      furni: [[14, 15]],
      stand: [[13, 17], [17, 17]],
      center: [15, 17],
    },
  };

  // 장식 화분(상호작용 없음, 몸통은 막힘 처리)
  var DECOR = [
    { sprite: "LARGE_PLANT", w: 2, h: 3, at: [28, 16] },
    { sprite: "PLANT", w: 1, h: 2, at: [1, 17] },
  ];

  // 에이전트 자리(home): [장소, stand 인덱스]. 없는 에이전트는 meeting_desk로 폴백.
  var SEATS = {
    researcher: ["whiteboard", 0],   // 화이트보드 한쪽
    critic: ["whiteboard", 1],       // 화이트보드 반대편(마주보게)
    expert: ["meeting_desk", 0],     // 회의 책상 왼쪽
    synthesizer: ["meeting_desk", 1],// 회의 책상 오른쪽(최종 발표)
    fact_checker: ["server_room", 0],// 도구실 PC 앞
  };

  var FURNI_FILES = ["BOOKSHELF", "WHITEBOARD", "COFFEE", "PC", "DESK", "LARGE_PLANT", "PLANT"];

  // ---- 유틸 ----
  function tileCenter(col, row) {
    // 캐릭터 발 기준 앵커: 타일 가로 중앙, 세로 하단.
    return { x: col * TILE + TILE / 2, y: row * TILE + TILE };
  }
  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }
  function nextFrame() { return new Promise(function (r) { requestAnimationFrame(function () { r(); }); }); }

  function loadImg(url) {
    return new Promise(function (resolve) {
      var img = new Image();
      img.onload = function () { resolve(img); };
      img.onerror = function () { resolve(null); }; // 실패해도 렌더는 계속
      img.src = url;
    });
  }

  // ---- Sprite: 캐릭터 상태머신 ----
  function Sprite(id, sheet, seatTile) {
    this.id = id;
    this.sheet = sheet;          // 스프라이트시트 Image(112×96) 또는 null
    this.seat = seatTile;        // {col,row}
    var c = tileCenter(seatTile.col, seatTile.row);
    this.px = c.x; this.py = c.y;
    this.tx = seatTile.col; this.ty = seatTile.row;
    this.state = "sit";          // idle|walk|sit|type|read|talk|wait
    this.dir = DIR.UP;           // 앉아서 가구를 바라봄
    this.flipX = false;
    this.path = [];              // 남은 경로 타일 [{col,row}...]
    this.animTime = 0;           // 상태 진입 후 누적 시간(초)
    this.standing = false;       // 서 있는가(인카운터 중)
    this._resolve = null;        // walkTo 완료 콜백
  }

  Sprite.prototype.setState = function (s) {
    if (this.state !== s) { this.state = s; this.animTime = 0; }
  };

  Sprite.prototype.face = function (dir, flip) {
    this.dir = dir; this.flipX = !!flip;
  };

  Sprite.prototype.sit = function () {
    this.standing = false;
    this.dir = DIR.UP;
    this.flipX = false;
    this.setState("sit");
  };

  // BFS 결과 경로를 따라 목적지로 이동. 완료 시 resolve되는 Promise 반환.
  Sprite.prototype.walkTo = function (path) {
    var self = this;
    // 이미 목적지면 즉시 완료
    if (!path || path.length === 0) {
      this.standing = true;
      this.setState("idle");
      return nextFrame();
    }
    this.path = path.slice();
    this.setState("walk");
    return new Promise(function (resolve) { self._resolve = resolve; });
  };

  Sprite.prototype.update = function (dt) {
    this.animTime += dt;
    if (this.state !== "walk" || this.path.length === 0) return;

    var target = this.path[0];
    var tc = tileCenter(target.col, target.row);
    var dx = tc.x - this.px, dy = tc.y - this.py;
    var dist = Math.sqrt(dx * dx + dy * dy);
    var step = WALK_SPEED * dt;

    // 이동 방향으로 dir/flip 갱신
    if (dist > 0.01) {
      if (Math.abs(tc.x - this.px) >= Math.abs(tc.y - this.py)) {
        this.dir = DIR.SIDE;
        this.flipX = (tc.x < this.px);
      } else {
        this.dir = (tc.y > this.py) ? DIR.DOWN : DIR.UP;
        this.flipX = false;
      }
    }

    if (dist <= step) {
      // 다음 타일에 도착
      this.px = tc.x; this.py = tc.y;
      this.tx = target.col; this.ty = target.row;
      this.path.shift();
      if (this.path.length === 0) {
        this.standing = true;
        this.setState("idle");
        var r = this._resolve; this._resolve = null;
        if (r) r();
      }
    } else {
      this.px += (dx / dist) * step;
      this.py += (dy / dist) * step;
    }
  };

  // 현재 상태의 스프라이트시트 프레임 열/행 및 픽셀 오프셋 계산
  Sprite.prototype.frameInfo = function () {
    var col = 0, dir = this.dir, ox = 0, oy = 0;
    var step = Math.floor(this.animTime * ANIM_FPS);
    switch (this.state) {
      case "walk":
        col = step % WALK_FRAMES;
        break;
      case "type":
        // 정지 프레임 + 미세 x 흔들림(키보드 두드림)
        col = 0; dir = DIR.UP; ox = (step % 2 === 0) ? -1 : 1;
        break;
      case "read":
        col = 0; dir = DIR.UP;
        break;
      case "talk":
        // 정지 프레임 + 위아래 hop(sine, 진폭 2px)
        col = 0; oy = -Math.abs(Math.sin(this.animTime * Math.PI * 3)) * 2;
        break;
      case "wait":
        col = 0; break;
      case "sit":
        col = 0; oy = -2; break; // 살짝 안착
      case "idle":
      default:
        col = 0; break;
    }
    return { col: col, dir: dir, ox: ox, oy: oy };
  };

  // ---- 엔진 본체 ----
  var Engine = {
    ready: Promise.resolve(),
    _inited: false,
    _canvas: null, _ctx: null,
    _static: null, _sctx: null,   // 정적 레이어(바닥+벽+가구) 오프스크린 캐시
    _bubbleLayer: null,
    _scale: 1,
    _imgs: {},                    // 가구/바닥 이미지
    _sheets: [],                  // char_0..5
    _sprites: {},                 // id -> Sprite
    _order: [],                   // 에이전트 id 순서
    _grid: null,                  // grid[row][col] 0=이동가능 1=막힘
    _activeLoc: null,
    _speaker: null,
    _participants: [],
    _bubble: null,                // {el, stext, spriteId}
    _colors: {},
    _soundOn: false,
    _sfx: {},
    _last: 0,
    _raf: 0,
  };

  // 공개: 초기화(META로 에이전트 구성). 이미지 로드 → 월드 빌드 → 루프 시작.
  Engine.init = function (meta) {
    var self = this;
    this._canvas = document.getElementById("stage");
    this._bubbleLayer = document.getElementById("bubbleLayer");
    if (!this._canvas) return Promise.resolve();
    this._ctx = this._canvas.getContext("2d");
    this._ctx.imageSmoothingEnabled = false;
    this._canvas.width = VW; this._canvas.height = VH;

    // 오프스크린 정적 레이어
    this._static = document.createElement("canvas");
    this._static.width = VW; this._static.height = VH;
    this._sctx = this._static.getContext("2d");
    this._sctx.imageSmoothingEnabled = false;

    this._order = Object.keys((meta && meta.agents) || {});
    if (this._order.length === 0) {
      this._order = ["researcher", "critic", "expert", "fact_checker", "synthesizer"];
    }

    // 사운드 준비(기본 off)
    this._loadSound();
    this._wireSoundButton();

    // 이미지 로드
    var jobs = [loadImg(ASSET + "floors/floor_0.png").then(function (im) { self._imgs.floor = im; })];
    FURNI_FILES.forEach(function (name) {
      jobs.push(loadImg(ASSET + "furniture/" + name + ".png").then(function (im) { self._imgs[name] = im; }));
    });
    for (var i = 0; i < CHAR_COUNT; i++) {
      (function (idx) {
        jobs.push(loadImg(ASSET + "characters/char_" + idx + ".png").then(function (im) { self._sheets[idx] = im; }));
      })(i);
    }

    this.ready = Promise.all(jobs).then(function () {
      self._buildGrid();
      self._spawnSprites();
      self._readColors();
      self._paintStatic();
      self._resize();
      window.addEventListener("resize", function () { self._resize(); });
      document.addEventListener("visibilitychange", function () {
        // 다시 보일 때 dt 튐 방지
        self._last = 0;
        if (!document.hidden) self._start();
      });
      self._inited = true;
      self._start();
    });
    return this.ready;
  };

  // 그리드/막힘 계산
  Engine._buildGrid = function () {
    var g = [];
    for (var r = 0; r < GH; r++) { g[r] = []; for (var c = 0; c < GW; c++) g[r][c] = 0; }
    // 벽: 상단 3줄 + 좌우 1줄
    for (var c2 = 0; c2 < GW; c2++) { g[0][c2] = 1; g[1][c2] = 1; g[2][c2] = 1; }
    for (var r2 = 0; r2 < GH; r2++) { g[r2][0] = 1; g[r2][GW - 1] = 1; }
    // 가구 몸통 막기
    function block(sp) {
      for (var y = 0; y < sp.h; y++) for (var x = 0; x < sp.w; x++) {
        var cc = sp.col + x, rr = sp.row + y;
        if (rr >= 0 && rr < GH && cc >= 0 && cc < GW) g[rr][cc] = 1;
      }
    }
    var self = this;
    Object.keys(STATIONS).forEach(function (id) {
      var st = STATIONS[id];
      st.furni.forEach(function (pos) { block({ col: pos[0], row: pos[1], w: st.w, h: st.h }); });
    });
    DECOR.forEach(function (d) { block({ col: d.at[0], row: d.at[1], w: d.w, h: d.h }); });
    // stand 타일은 강제 이동가능
    Object.keys(STATIONS).forEach(function (id) {
      STATIONS[id].stand.forEach(function (s) { g[s[1]][s[0]] = 0; });
    });
    this._grid = g;
  };

  // 에이전트 스프라이트 생성(자리에 sit)
  Engine._spawnSprites = function () {
    var self = this;
    this._sprites = {};
    this._order.forEach(function (id, i) {
      var seatDef = SEATS[id] || ["meeting_desk", i % 2];
      var st = STATIONS[seatDef[0]] || STATIONS.meeting_desk;
      var s = st.stand[seatDef[1]] || st.stand[0];
      var sheet = self._sheets[i % CHAR_COUNT] || null;
      self._sprites[id] = new Sprite(id, sheet, { col: s[0], row: s[1] });
    });
  };

  // ---- BFS 경로탐색 ----
  Engine._bfs = function (start, goal) {
    if (start.col === goal.col && start.row === goal.row) return [];
    var g = this._grid;
    var key = function (c, r) { return r * GW + c; };
    var q = [start], head = 0;
    var visited = {}; visited[key(start.col, start.row)] = true;
    var parent = {};
    var dirs = [[1, 0], [-1, 0], [0, 1], [0, -1]];
    while (head < q.length) {
      var cur = q[head++];
      if (cur.col === goal.col && cur.row === goal.row) {
        // 경로 복원
        var path = [], k = key(cur.col, cur.row), node = cur;
        while (!(node.col === start.col && node.row === start.row)) {
          path.push({ col: node.col, row: node.row });
          node = parent[key(node.col, node.row)];
          if (!node) break;
        }
        path.reverse();
        return path;
      }
      for (var d = 0; d < 4; d++) {
        var nc = cur.col + dirs[d][0], nr = cur.row + dirs[d][1];
        if (nc < 0 || nc >= GW || nr < 0 || nr >= GH) continue;
        if (g[nr][nc] === 1) continue;
        var nk = key(nc, nr);
        if (visited[nk]) continue;
        visited[nk] = true;
        parent[nk] = cur;
        q.push({ col: nc, row: nr });
      }
    }
    // 도달 불가 → 직행 폴백(한 칸 목적지)
    return [{ col: goal.col, row: goal.row }];
  };

  Engine._walk = function (sprite, goalTile) {
    var path = this._bfs({ col: sprite.tx, row: sprite.ty }, { col: goalTile[0], row: goalTile[1] });
    return sprite.walkTo(path);
  };

  // ---- 정적 레이어(바닥/벽/가구) 그리기 → 캐시 ----
  Engine._paintStatic = function () {
    var ctx = this._sctx, col = this._colors;
    ctx.clearRect(0, 0, VW, VH);
    // 바닥
    if (this._imgs.floor) {
      for (var r = 0; r < GH; r++) for (var c = 0; c < GW; c++) {
        ctx.drawImage(this._imgs.floor, c * TILE, r * TILE, TILE, TILE);
      }
    } else {
      ctx.fillStyle = col.floor1 || "#ecdfc6";
      ctx.fillRect(0, 0, VW, VH);
    }
    // 바닥 틴트(테마)
    if (col.floorTint) { ctx.fillStyle = col.floorTint; ctx.fillRect(0, 0, VW, VH); }
    // 절차적 벽(상단 3줄 + 좌우 1줄)
    this._paintWalls(ctx, col);
    // 가구
    var self = this;
    Object.keys(STATIONS).forEach(function (id) {
      var st = STATIONS[id];
      var img = self._imgs[st.sprite];
      if (!img) return;
      st.furni.forEach(function (pos) {
        ctx.drawImage(img, pos[0] * TILE, pos[1] * TILE, st.w * TILE, st.h * TILE);
      });
    });
    DECOR.forEach(function (d) {
      var img = self._imgs[d.sprite];
      if (img) ctx.drawImage(img, d.at[0] * TILE, d.at[1] * TILE, d.w * TILE, d.h * TILE);
    });
  };

  Engine._paintWalls = function (ctx, col) {
    var wall = col.wall || "#d9c6a4", wall2 = col.wall2 || "#cdb691";
    // 상단 3줄
    ctx.fillStyle = wall;
    ctx.fillRect(0, 0, VW, 3 * TILE);
    // 좌우 1줄
    ctx.fillRect(0, 0, TILE, VH);
    ctx.fillRect(VW - TILE, 0, TILE, VH);
    // 벽 하단 걸레받이(2px 밝은 라인)로 입체감
    ctx.fillStyle = wall2;
    ctx.fillRect(0, 3 * TILE - 2, VW, 2);               // 상단벽 아래
    ctx.fillRect(TILE - 2, 0, 2, VH);                   // 좌측벽 안쪽
    ctx.fillRect(VW - TILE, 0, 2, VH);                  // 우측벽 안쪽
    // 상단벽 위쪽 그림자 라인
    ctx.fillStyle = "rgba(0,0,0,0.10)";
    ctx.fillRect(0, 3 * TILE, VW, 2);
  };

  Engine._readColors = function () {
    var cs = getComputedStyle(document.documentElement);
    function v(name, fb) { var x = cs.getPropertyValue(name); return (x && x.trim()) || fb; }
    this._colors = {
      wall: v("--wall", "#d9c6a4"),
      wall2: v("--wall2", "#cdb691"),
      floor1: v("--floor1", "#ecdfc6"),
      floorTint: v("--floorTint", "rgba(240,222,186,0.34)"),
      accent: v("--accent", "#4f7cff"),
      dark: (document.documentElement.getAttribute("data-theme") === "dark"),
    };
  };

  // ---- 스케일/리사이즈(정수배) ----
  Engine._resize = function () {
    var wrap = this._canvas.parentElement;
    var avail = wrap ? wrap.clientWidth : VW;
    var scale = Math.max(1, Math.floor(avail / VW));
    // 폭이 512 미만이면(모바일) 정수배 대신 폭 맞춤(픽셀퍼펙트는 유지 불가하나 깨지지 않게)
    if (avail < VW) { scale = avail / VW; }
    this._scale = scale;
    var cssW = Math.round(VW * scale), cssH = Math.round(VH * scale);
    this._canvas.style.width = cssW + "px";
    this._canvas.style.height = cssH + "px";
    if (this._bubbleLayer) {
      this._bubbleLayer.style.width = cssW + "px";
      this._bubbleLayer.style.height = cssH + "px";
    }
  };

  // ---- 게임 루프 ----
  Engine._start = function () {
    var self = this;
    cancelAnimationFrame(this._raf);
    var loop = function (now) {
      self._raf = requestAnimationFrame(loop);
      if (document.hidden) { self._last = now; return; }   // 숨김 시 일시정지
      if (!self._last) self._last = now;
      var dt = (now - self._last) / 1000;
      self._last = now;
      if (dt > 0.1) dt = 0.1;   // 탭 복귀 등 튐 방지
      self._update(dt);
      self._render();
      self._positionBubble();
    };
    this._raf = requestAnimationFrame(loop);
  };

  Engine._update = function (dt) {
    var s = this._sprites;
    for (var id in s) if (s.hasOwnProperty(id)) s[id].update(dt);
  };

  Engine._render = function () {
    var ctx = this._ctx;
    ctx.clearRect(0, 0, VW, VH);
    ctx.drawImage(this._static, 0, 0);            // 캐시된 바닥/벽/가구
    // 활성 장소 하이라이트(바닥 링)
    if (this._activeLoc && STATIONS[this._activeLoc]) {
      var st = STATIONS[this._activeLoc];
      var cx = 0, cy = 0, n = st.stand.length;
      st.stand.forEach(function (p) { cx += p[0] * TILE + TILE / 2; cy += p[1] * TILE + TILE / 2; });
      cx /= n; cy /= n;
      ctx.save();
      ctx.strokeStyle = this._colors.accent;
      ctx.globalAlpha = 0.8;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.ellipse(cx, cy + 6, 26, 10, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }
    // 에이전트: y 정렬(뒤에 있는 게 먼저)
    var list = [];
    for (var id in this._sprites) if (this._sprites.hasOwnProperty(id)) list.push(this._sprites[id]);
    list.sort(function (a, b) { return a.py - b.py; });
    for (var i = 0; i < list.length; i++) this._drawSprite(list[i]);
  };

  Engine._drawSprite = function (sp) {
    var ctx = this._ctx;
    var fi = sp.frameInfo();
    var baseX = Math.round(sp.px - FRAME_W / 2 + fi.ox);
    var baseY = Math.round(sp.py - FRAME_H + fi.oy);

    // 그림자
    ctx.save();
    ctx.fillStyle = this._colors.dark ? "rgba(0,0,0,0.5)" : "rgba(0,0,0,0.28)";
    var shW = (sp.state === "walk") ? 8 : 10;
    ctx.beginPath();
    ctx.ellipse(Math.round(sp.px), Math.round(sp.py) - 2, shW, 3, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    // 스프라이트 프레임
    if (sp.sheet) {
      var sx = fi.col * FRAME_W, sy = fi.dir * FRAME_H;
      if (sp.flipX) {
        ctx.save();
        ctx.translate(baseX + FRAME_W, baseY);
        ctx.scale(-1, 1);
        ctx.drawImage(sp.sheet, sx, sy, FRAME_W, FRAME_H, 0, 0, FRAME_W, FRAME_H);
        ctx.restore();
      } else {
        ctx.drawImage(sp.sheet, sx, sy, FRAME_W, FRAME_H, baseX, baseY, FRAME_W, FRAME_H);
      }
    } else {
      // 시트 로드 실패 폴백: 색 블록
      ctx.fillStyle = "#888";
      ctx.fillRect(baseX + 3, baseY + 6, 10, 24);
    }

    // 발언자 강조 링
    if (this._speaker === sp.id) {
      ctx.save();
      ctx.strokeStyle = this._colors.accent;
      ctx.globalAlpha = 0.9;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.ellipse(Math.round(sp.px), Math.round(sp.py) - 1, 11, 4, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    // wait 상태: 머리 위 "!" 표시
    if (sp.state === "wait") {
      ctx.save();
      ctx.fillStyle = this._colors.accent;
      ctx.font = "bold 12px monospace";
      ctx.textAlign = "center";
      ctx.fillText("!", Math.round(sp.px), baseY - 2);
      ctx.restore();
    }
  };

  // ---- 말풍선 오버레이 ----
  Engine._positionBubble = function () {
    if (!this._bubble) return;
    var sp = this._sprites[this._bubble.spriteId];
    if (!sp) return;
    var sc = this._scale;
    var x = sp.px * sc;
    var y = (sp.py - FRAME_H - 6) * sc; // 머리 위
    this._bubble.el.style.left = x + "px";
    this._bubble.el.style.top = y + "px";
  };

  // ---- 공개 API (server.py reveal()이 호출) ----

  // 전원 자리에 sit(즉시), 말풍선/강조/활성장소 초기화
  Engine.reset = function () {
    for (var id in this._sprites) if (this._sprites.hasOwnProperty(id)) {
      var sp = this._sprites[id];
      var c = tileCenter(sp.seat.col, sp.seat.row);
      sp.px = c.x; sp.py = c.y; sp.tx = sp.seat.col; sp.ty = sp.seat.row;
      sp.path = []; sp._resolve = null;
      sp.sit();
    }
    this._activeLoc = null;
    this._speaker = null;
    this._participants = [];
    this.clearSpeech();
  };

  // 두 에이전트가 장소 stand로 걸어가 마주봄. 도착 시 resolve.
  Engine.encounter = function (ids, locId) {
    var self = this;
    this._playSfx("click");
    var st = STATIONS[locId] || STATIONS.meeting_desk;
    this._activeLoc = STATIONS[locId] ? locId : null;
    this._participants = ids.slice();
    var proms = ids.map(function (id, i) {
      var sp = self._sprites[id];
      if (!sp) return Promise.resolve();
      var goal = st.stand[i] || st.stand[0];
      return self._walk(sp, goal);
    });
    return Promise.all(proms).then(function () {
      // 마주보기: 첫 사람은 오른쪽, 둘째는 왼쪽
      if (ids.length > 1) {
        if (self._sprites[ids[0]]) self._sprites[ids[0]].face(DIR.SIDE, false);
        if (self._sprites[ids[1]]) self._sprites[ids[1]].face(DIR.SIDE, true);
      } else if (self._sprites[ids[0]]) {
        self._sprites[ids[0]].face(DIR.DOWN, false);
      }
    });
  };

  // 인카운터 종료: 참가자 자리로 복귀 → sit
  Engine.endEncounter = function (ids) {
    var self = this;
    this.clearSpeaking();
    this.clearSpeech();
    this._activeLoc = null;
    var who = (ids && ids.length) ? ids : this._participants;
    var proms = (who || []).map(function (id) {
      var sp = self._sprites[id];
      if (!sp) return Promise.resolve();
      return self._walk(sp, [sp.seat.col, sp.seat.row]).then(function () { sp.sit(); });
    });
    this._participants = [];
    return Promise.all(proms);
  };

  // 발언자 지정 → talk 상태(hop). 타이핑 중 호출.
  Engine.setSpeaking = function (id) {
    this._speaker = id;
    var sp = this._sprites[id];
    if (sp && sp.standing) sp.setState("talk");
  };
  Engine.clearSpeaking = function () {
    this._speaker = null;
    for (var id in this._sprites) if (this._sprites.hasOwnProperty(id)) {
      var sp = this._sprites[id];
      if (sp.standing && (sp.state === "talk")) sp.setState("idle");
    }
  };

  // 말풍선 표시 → 타이핑용 .stext 노드 반환(server.py의 typeInto가 채움)
  Engine.showSpeech = function (id) {
    this.clearSpeech();
    if (!this._bubbleLayer || !this._sprites[id]) return null;
    var el = document.createElement("div");
    el.className = "pix-bubble";
    var span = document.createElement("span");
    span.className = "stext";
    el.appendChild(span);
    this._bubbleLayer.appendChild(el);
    this._bubble = { el: el, stext: span, spriteId: id };
    this._positionBubble();
    return span;
  };
  Engine.clearSpeech = function () {
    if (this._bubble && this._bubble.el && this._bubble.el.parentNode) {
      this._bubble.el.parentNode.removeChild(this._bubble.el);
    }
    this._bubble = null;
  };

  Engine.activateLoc = function (id) {
    this._activeLoc = (id && STATIONS[id]) ? id : null;
  };

  // 파이널: synthesizer가 화이트보드 앞으로 나와 발표(read)
  Engine.finalize = function () {
    var self = this;
    this._playSfx("chime");
    var sp = this._sprites["synthesizer"];
    var wb = STATIONS.whiteboard;
    var center = wb.center || wb.stand[0];
    if (!sp) return Promise.resolve();
    this._activeLoc = "whiteboard";
    return this._walk(sp, center).then(function () {
      sp.standing = true;
      sp.setState("read");
    });
  };

  Engine.onThemeChange = function () {
    if (!this._inited) return;
    this._readColors();
    this._paintStatic();
  };

  // ---- 사운드 ----
  Engine._loadSound = function () {
    try {
      this._sfx.click = new Audio(ASSET + "sfx/click.wav");
      this._sfx.chime = new Audio(ASSET + "sfx/chime.wav");
      this._sfx.click.preload = "auto";
      this._sfx.chime.preload = "auto";
    } catch (e) {}
    try { this._soundOn = localStorage.getItem("pixel_sound") === "1"; } catch (e) {}
  };
  Engine._wireSoundButton = function () {
    var btn = document.getElementById("soundBtn");
    if (!btn) return;
    var self = this;
    var paint = function () { btn.textContent = self._soundOn ? "🔊 소리" : "🔇 소리"; };
    paint();
    btn.addEventListener("click", function () {
      self._soundOn = !self._soundOn;
      try { localStorage.setItem("pixel_sound", self._soundOn ? "1" : "0"); } catch (e) {}
      paint();
    });
  };
  Engine.setSound = function (on) { this._soundOn = !!on; };
  Engine._playSfx = function (name) {
    if (!this._soundOn) return;
    var a = this._sfx[name];
    if (!a) return;
    try { a.currentTime = 0; a.play().catch(function () {}); } catch (e) {}
  };

  window.PixelOffice = Engine;
})();
