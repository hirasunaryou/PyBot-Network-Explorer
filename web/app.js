"use strict";
/* This is a viewer of UNMODIFIED PyBot. Dynamic edges are observed in a
 * separate replay; static edges are from AST imports. The two never mix. */
(function () {
  const $=id=>document.getElementById(id);
  const NS="http://www.w3.org/2000/svg";
  const upstream="https://github.com/huggingface/pybot/blob/7d63c7fbebb44c7e466e5c8b5c1f341ab767929e/";
  const stages={
    runtime:"実行の制御",understanding:"入力の理解",memory:"会話・記憶",
    knowledge:"知識・計算",compose:"回答の組み立て",
    modules:"回答候補",arbiter:"候補の選択"
  };
  const centers={
    runtime:[135,315],understanding:[345,170],memory:[346,451],
    knowledge:[577,177],compose:[588,465],
    modules:[835,250],arbiter:[1004,449]
  };
  const state={
    session:"graph_"+Math.random().toString(36).slice(2)+Math.random().toString(36).slice(2),
    turns:[],turnIndex:-1,trace:null,system:null,
    view:"system",density:45,activeFrame:0,playing:null,speed:1,
    selected:null,nodes:[],edges:[],nodeCache:new Map(),
    zoom:1,offsetX:0,offsetY:0,drag:null,busy:false,requestId:0,
    font:1,theme:"dark",expanded:false
  };
  function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
  async function request(path,post){
    const options=post===undefined?{}:{
      method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(post)
    };
    const response=await fetch(path,options);
    let data;try{data=await response.json();}catch(_){throw Error("JSON応答を取得できませんでした");}
    if(!response.ok||data.error)throw Error(data.error||"HTTP "+response.status);
    return data;
  }
  function text(id,value){$(id).textContent=String(value==null?"":value);}
  function toast(message){
    const box=$("toast");box.textContent=message;box.classList.remove("hidden");
    clearTimeout(toast.timer);toast.timer=setTimeout(()=>box.classList.add("hidden"),4800);
  }
  function status(s){text("statusLine",s);}
  function number(n){return Number(n||0).toLocaleString("ja-JP");}
  function hash(input){
    let n=2166136261;for(const c of String(input)){n^=c.charCodeAt(0);n=Math.imul(n,16777619);}
    return n>>>0;
  }
  function svg(tag,attrs){
    const el=document.createElementNS(NS,tag);
    for(const [key,val] of Object.entries(attrs||{}))el.setAttribute(key,String(val));
    return el;
  }
  function moveCamera(){ $("graphScene").setAttribute("transform",
      "translate("+state.offsetX+" "+state.offsetY+") scale("+state.zoom+")");}
  function cameraReset(){state.zoom=1;state.offsetX=0;state.offsetY=0;moveCamera();}
  function cameraZoom(factor,x=570,y=320){
    const previous=state.zoom;
    state.zoom=Math.max(.55,Math.min(3.7,state.zoom*factor));
    state.offsetX=x-(x-state.offsetX)*state.zoom/previous;
    state.offsetY=y-(y-state.offsetY)*state.zoom/previous;
    moveCamera();
  }
  function setBusy(busy){
    state.busy=busy;
    $("sendQuestion").disabled=busy;
    $("clearChat").disabled=busy;
    $("visualize").disabled=busy||state.turnIndex<0;
    text("inputHint",busy?"実PyBotを処理中…":"Enterで送信・Shift+Enterで改行");
  }
  function toastError(error){
    const msg=error&&error.message||String(error);toast("処理に失敗: "+msg);
    status("エラー: "+msg);
  }

  function selectedViewData(){
    if(state.view==="system")return state.system&&state.system.groups;
    if(state.view==="files")return state.system&&state.system.files;
    return state.trace&&state.trace.graph;
  }
  function pickNodes(data){
    if(!data)return [];
    if(state.view==="system")return data.nodes;
    const all=data.nodes||[];
    const groups=all.filter(n=>n.kind==="group");
    const others=all.filter(n=>n.kind!=="group");
    const target=Math.max(10,state.density-groups.length);
    const chosen=others.slice(0,target);
    const active=state.trace&&state.trace.frames[state.activeFrame]&&state.trace.frames[state.activeFrame].node;
    if(state.view==="trace"&&active&&!chosen.some(n=>n.id===active)){
      const match=others.find(n=>n.id===active);
      if(match){if(chosen.length>=target)chosen.pop();chosen.push(match);}
    }
    return groups.concat(chosen);
  }

  function computeCoordinates(nodes){
    const byGroup={};
    for(const n of nodes){const group=n.group||"runtime";(byGroup[group] ||= []).push(n);}
    const positions=new Map();
    for(const [group,groupNodes] of Object.entries(byGroup)){
      const center=centers[group]||[565,320];
      const anchor=groupNodes.filter(n=>n.kind==="group");
      const children=groupNodes.filter(n=>n.kind!=="group");
      for(const g of anchor)positions.set(g.id,{x:center[0],y:center[1]});
      // A slightly skewed radial bundle clusters functions/files by purpose.
      const count=children.length;
      children.forEach((n,i)=>{
        const noise=hash(n.id);
        const radius=Math.min(114,35+Math.sqrt(i+1)*13);
        const theta=i*2.39996323 + (noise%19)/40;
        const x=center[0]+Math.cos(theta)*radius;
        const y=center[1]+Math.sin(theta)*radius*.82;
        positions.set(n.id,{x:Math.max(38,Math.min(1104,x)),y:Math.max(57,Math.min(600,y))});
      });
    }
    return positions;
  }
  function linkPath(a,b){
    if(!a||!b)return "";
    const dx=b.x-a.x,dy=b.y-a.y;
    if(Math.abs(dx)+Math.abs(dy)<2)
      return "M"+a.x+","+a.y+" c -22,-45 27,-65 28,0";
    const curve=Math.min(80,Math.abs(dx)*.33);
    return "M"+a.x+","+a.y+" C"+(a.x+curve)+","+(a.y-dy*.12)+" "+(b.x-curve)+","+(b.y+dy*.12)+" "+b.x+","+b.y;
  }

  function label(n){
    if(n.kind==="group")return stages[n.group]||n.name;
    if(n.kind==="function")return n.name+"()";
    const base=n.file||n.name||n.id;
    return base.split("/").pop();
  }

  function renderGraph(){
    const data=selectedViewData();
    const edgeRoot=$("edges"),nodeRoot=$("nodes");
    edgeRoot.replaceChildren();nodeRoot.replaceChildren();
    if(!data){$("graphEmpty").classList.remove("hidden");return;}
    const nodes=pickNodes(data);
    const known=new Set(nodes.map(n=>n.id));
    $("graphEmpty").classList.toggle("hidden",nodes.length!==0);
    const coords=computeCoordinates(nodes);
    const frame=state.trace&&state.trace.frames[state.activeFrame];
    const activeNode=state.view==="trace"&&frame&&frame.node||null;
    const relevantEdges=(data.edges||[]).filter(e=>known.has(e.source)&&known.has(e.target));
    const related=new Set();
    for(const e of relevantEdges){
      if(e.source===activeNode||e.target===activeNode){related.add(e.source);related.add(e.target);}
    }
    state.nodes=nodes;state.edges=relevantEdges;
    const edgeLimit=state.view==="files"?200:400;
    for(const e of relevantEdges.slice(0,edgeLimit)){
      const a=coords.get(e.source),b=coords.get(e.target);
      if(!a||!b)continue;
      const active=e.source===activeNode||e.target===activeNode;
      const element=svg("path",{
        "d":linkPath(a,b),
        "class":"graph-link "+(e.type==="static_import"||e.type==="member"?"static":"observed")+(active?" active":"")+
           (related.has(e.source)&&related.has(e.target)?" related":""),
        "stroke-width":Math.min(4,1+Math.log1p(e.calls||1)/5)
      });
      const title=svg("title");title.textContent=(e.type==="observed"?
        "再実行で観測された関数呼び出し":"静的依存／ファイルの所属")+
        " · "+number(e.calls)+"回（あるいは規模）";
      element.appendChild(title);
      edgeRoot.appendChild(element);
    }
    const ranking=nodes.filter(n=>n.kind!=="group").sort((a,b)=>(b.calls||b.lines||0)-(a.calls||a.lines||0));
    const titles=new Set(ranking.slice(0,state.view==="trace"?16:12).map(n=>n.id));
    for(const n of nodes){
      const p=coords.get(n.id);
      const isGroup=n.kind==="group";
      const isSelected=state.selected&&state.selected.id===n.id;
      const isActive=activeNode===n.id;
      const connected=related.has(n.id);
      const radius=isGroup?26:Math.max(6,Math.min(14,6+Math.log1p(n.calls||n.lines||1)/2.1));
      const g=svg("g",{
        class:"graph-node"+(isSelected?" selected":"")+(isActive?" active":""),
        transform:"translate("+p.x+" "+p.y+")",tabindex:"0",role:"button",
        "aria-label":label(n)+"を詳しく見る", "data-group":n.group
      });
      g.append(svg("circle",{class:"halo",r:radius+7}));
      g.append(svg("circle",{class:"main",r:radius,opacity:state.view==="trace"&&activeNode&&!isActive&&!connected?".8":"1"}));
      const name=label(n);
      if(isGroup||isActive||isSelected||titles.has(n.id)){
        const t=svg("text",{x:0,y:radius+17,"text-anchor":"middle"});
        t.textContent=name.length>20?name.slice(0,18)+"…":name;
        g.append(t);
      }
      if(isGroup){
        const counter=svg("text",{class:"stat",x:0,y:radius+31,"text-anchor":"middle"});
        counter.textContent=number(n.files)+" files";
        g.append(counter);
      }
      const tip=svg("title");
      tip.textContent=name+" / "+(n.file||n.group)+
        (n.calls!==undefined?" / "+number(n.calls)+" observed calls":"");
      g.appendChild(tip);
      g.addEventListener("click",()=>selectNode(n,true));
      g.addEventListener("keydown",event=>{
        if(event.key==="Enter"||event.key===" "){event.preventDefault();selectNode(n,true);}
      });
      nodeRoot.appendChild(g);
    }
    moveCamera();
    const totals=state.view==="trace"&&state.trace?
      number(state.trace.call_count)+"回の関数呼出し / "+number(state.trace.graph.observed_node_count)+"種類の関数":
      number(state.system&&state.system.total.files)+"個のPythonファイルを解析";
    status(totals+" · 描画 "+nodes.length+"ノード / "+Math.min(relevantEdges.length,edgeLimit)+"エッジ（見やすさのため抽出）");
  }
  function view(mode){
    if(mode==="trace"&&!state.trace){toast("まず質問し、「この回答のネットワークを見る」をクリックしてください。");return;}
    state.view=mode;
    for(const button of document.querySelectorAll("[data-mode]")){
      const active=button.dataset.mode===mode;
      button.classList.toggle("active",active);
      button.setAttribute("aria-selected",String(active));
    }
    $("graphSource").innerHTML=mode==="trace"?
      '<span class="evidence-key dynamic"></span> 動的グラフ / 別メモリで再実行したPyBot':
      '<span class="evidence-key static"></span> 静的グラフ / 元コードの構造・import関係';
    $("evidenceBadge").textContent=mode==="trace"?"REPLAY":"STATIC";
    $("playbackTitle").textContent=mode==="trace"?"OBSERVED EXECUTION PATH":"STATIC SYSTEM MAP";
    $("playbackSubtitle").textContent=mode==="trace"?
      "再生位置の関数が光ります。矢印で前後へ。":"構造の可能性を示す図。実行された関数ではありません。";
    const enabled=mode==="trace"&&state.trace&&state.trace.frames.length>0;
    for(const id of ["timeline","goFirst","goBack","play","goNext","goLast","speed"])$(id).disabled=!enabled;
    cameraReset();
    renderGraph();
  }
  function renderChat(){
    const area=$("chat");area.replaceChildren();
    if(!state.turns.length){
      const div=document.createElement("div");div.className="chat-empty";
      div.innerHTML='<div class="chat-empty-art">◎</div><strong>ここから実験を始める</strong><p>「平均値の説明」を選ぶと、実際の回答文が記述されたPythonの行も調べられます。</p>';
      area.append(div);return;
    }
    state.turns.forEach((turn,i)=>{
      for(const [isUser,body] of [[true,turn.user],[false,turn.reply]]){
        const row=document.createElement("div");
        row.className="chat-turn"+(isUser?" user":"");
        const bubble=document.createElement("div");
        bubble.className="chat-bubble";bubble.textContent=body;
        row.append(bubble);
        if(!isUser){
          const info=document.createElement("div");info.className="chat-metadata";
          const meta=document.createElement("span");meta.textContent=
            (turn.selected_module||"fallback")+" · "+number(turn.elapsed_ms)+" ms";
          info.append(meta);
          const button=document.createElement("button");
          button.textContent="経路を調べる ↗";
          button.onclick=()=>{selectTurn(i);analyze();};
          info.append(button);row.append(info);
        }
        area.append(row);
      }
    });
    area.scrollTop=area.scrollHeight;
  }
  function selectTurn(index){
    if(!state.turns[index])return;
    state.turnIndex=index;
    const turn=state.turns[index];
    $("candidateMeta").textContent=turn.candidates.length+"件 · "+(turn.selected_module||"fallback")+" 採択";
    $("candidates").replaceChildren();
    if(!turn.candidates.length){
      const span=document.createElement("div");span.className="muted";span.textContent="候補なし・PyBot既定応答";
      $("candidates").append(span);
    }
    for(const [i,c] of turn.candidates.entries()){
      const row=document.createElement("div");row.className="candidate"+(i===turn.chosen_index?" selected":"");
      const left=document.createElement("b");left.textContent=(i===turn.chosen_index?"採択 ✓ ":"")+c.module;
      const right=document.createElement("small");right.textContent="PRIORITY "+c.priority;
      row.append(left,right);row.title=c.reply;$("candidates").append(row);
    }
    $("visualize").disabled=false;
    state.trace=null;
    clearInterval(state.playing);state.playing=null;
    $("play").textContent="▶ 再生";
    $("timeline").value="0";
    if(state.view==="trace")view("system");
  }
  async function ask(){
    const input=$("questionInput").value.trim();
    if(!input||state.busy)return;
    setBusy(true);
    try{
      const turn=await request("/api/ask",{session:state.session,text:input});
      state.turns.push(turn);
      $("questionInput").value="";
      selectTurn(state.turns.length-1);
      renderChat();
      toast("PyBot純正の回答を取得しました。経路を解析できます。");
    }catch(error){toastError(error);}finally{setBusy(false);}
  }
  async function analyze(){
    if(state.turnIndex<0||state.busy)return;
    setBusy(true);
    status("元のPyBotを別メモリで再実行し、関数呼び出しを記録しています…");
    try{
      const trace=await request("/api/trace",{session:state.session,turn_index:state.turnIndex});
      state.trace=trace;
      state.activeFrame=0;
      $("timeline").min="0";$("timeline").max=String(Math.max(1,trace.frames.length-1));
      $("timeline").value="0";
      text("playbackCount",number(trace.call_count)+" calls");
      const ratio=trace.replay_equal?"再実行一致":"再実行不一致 ⚠";
      $("playbackSubtitle").textContent=
        ratio+" · "+number(trace.graph.observed_node_count)+"関数 · "+number(trace.frames.length)+"コマ";
      if(!trace.replay_equal)toast(trace.warning);
      renderOrigin();
      view("trace");
      if(trace.frames.length)frameAt(0);
    }catch(error){toastError(error);}
    finally{setBusy(false);}
  }
  function renderOrigin(){
    const box=$("answerOrigin");box.replaceChildren();
    const matches=state.trace&&state.trace.source_matches||[];
    if(!matches.length){box.textContent="元回答と完全一致するPythonの文字列定数は見つかりませんでした。関数グラフからコードを辿れます。";return;}
    for(const source of matches){
      const item=document.createElement("div");item.className="origin-found";
      const header=document.createElement("strong");
      header.textContent=source.symbol+" · 元回答と完全一致";
      item.append(header);
      const button=document.createElement("button");
      button.textContent=source.path+":"+source.line+" を開く ↗";
      button.onclick=()=>inspectFile(source.path,source.line);
      item.append(button);
      const foot=document.createElement("p");
      foot.textContent="静的文字列の一致です（この行が実行された証拠ではありません）。"+
        (source.references.length?" 返却コード候補 L"+source.references.join(", L"):"");
      item.append(foot);box.append(item);
    }
  }
  function frameAt(position){
    if(!state.trace||!state.trace.frames.length)return;
    const frames=state.trace.frames;
    const index=Math.max(0,Math.min(frames.length-1,Math.round(position)));
    state.activeFrame=index;
    $("timeline").value=String(index);
    const f=frames[index];
    text("frameLabel",""+(index+1)+"/"+frames.length+" · "+f.phase+" · "+Number(f.ms||0).toFixed(1)+"ms");
    const same=state.trace.graph.nodes.find(n=>n.id===f.node);
    const shown=same||{
      id:f.node,group:f.file?stageFromPath(f.file):"runtime",
      file:f.file,name:f.fn,line:f.line,kind:"function"
    };
    selectNode(shown,false);
    if(state.view==="trace")renderGraph();
    if(index===frames.length-1)pause();
  }
  function stageFromPath(path){
    if(path==="bot/modules/arbiter.py")return "arbiter";
    return path.split("/")[1]||"runtime";
  }
  function pause(){
    if(state.playing!==null)clearInterval(state.playing);
    state.playing=null;$("play").textContent="▶ 再生";
  }
  function playback(){
    if(!state.trace)return;
    if(state.playing!==null){pause();return;}
    if(state.activeFrame>=state.trace.frames.length-1)frameAt(0);
    $("play").textContent="Ⅱ 停止";
    state.playing=setInterval(()=>{
      if(state.activeFrame>=state.trace.frames.length-1){pause();return;}
      frameAt(state.activeFrame+1);
    },Math.max(36,200/state.speed));
  }
  async function selectNode(node,manual){
    state.selected=node;
    const isGroup=node.kind==="group";
    const labelText=isGroup?(stages[node.group]||node.group):label(node);
    text("selectedTitle",labelText);
    const group=node.group||stageFromPath(node.file||"");
    let description={
      runtime:"PyBotが各フェーズを呼び出す中枢です。",
      understanding:"入力を解釈するための規則や読み取り処理です。",
      memory:"名前・話題・過去の会話などを扱うコードです。",
      knowledge:"計算・知識辞書・検索に関するPythonコードです。",
      compose:"回答文の組み立て・言い換えに関するコードです。",
      modules:"回答候補を提案する複数のモジュールです。",
      arbiter:"複数の候補から1つを選ぶ回答選択器です。"
    }[group]||"PyBotのコードの一部です。";
    text("selectedExplain",description+(node.kind==="function"?
      " 関数の正確な目的は元ソースを確認してください。":""));
    const facts=$("nodeFacts");facts.replaceChildren();
    for(const [label,value] of (isGroup?
      [["分類",group],["ファイル",number(node.files)],["コード行数",number(node.lines)],
       ["関数",number(node.functions)]]:
      [["分類",group],["ファイル",node.file||"—"],
       ["行",node.line||"—"],[node.calls!==undefined?"実行回数":"行数",number(node.calls??node.lines||0)]])){
      const row=document.createElement("div");row.className="fact";
      const left=document.createElement("span");left.textContent=label;
      const right=document.createElement("b");right.textContent=value;
      row.append(left,right);facts.append(row);
    }
    if(node.file){
      await inspectFile(node.file,node.line||1,!manual);
    }else{
      text("sourcePath","グループ全体（ソースを選ぶと表示）");
      $("sourceCode").innerHTML='<div class="code-placeholder">表示ビューを「ファイル」にすると、領域内のPythonファイルを選べます。</div>';
      $("sourceLink").href="https://github.com/huggingface/pybot";
    }
    if(manual)renderGraph();
  }
  async function inspectFile(file,line=1,quiet=false){
    if(!/^bot\/[a-zA-Z0-9_/]+\.py$/.test(file))return;
    const requestId=++state.requestId;
    text("sourcePath",file+" : L"+line);
    $("sourceLink").href=upstream+file+"#L"+line;
    $("sourceCode").textContent="実ソースを読み込んでいます…";
    const key=file+":"+line;
    let data=state.nodeCache.get(key);
    try{
      if(!data){
        data=await request("/api/source?path="+encodeURIComponent(file)+"&line="+encodeURIComponent(line));
        state.nodeCache.set(key,data);
        if(state.nodeCache.size>160)state.nodeCache.delete(state.nodeCache.keys().next().value);
      }
      if(requestId!==state.requestId)return;
      const area=$("sourceCode");area.replaceChildren();
      for(const row of data.lines){
        const lineEl=document.createElement("div");lineEl.className="source-row"+(row.line===Number(line)?" focus":"");
        const counter=document.createElement("span");counter.className="line-no";counter.textContent=row.line;
        const code=document.createElement("code");code.textContent=row.code;
        lineEl.append(counter,code);area.append(lineEl);
      }
      const focus=area.querySelector(".focus");
      if(focus)area.scrollTop=Math.max(0,focus.offsetTop-area.offsetTop-area.clientHeight*.3);
    }catch(error){
      if(requestId===state.requestId){text("sourceCode","ソースを表示できません: "+error.message);}
      if(!quiet)toastError(error);
    }
  }
  async function loadSystem(){
    try{
      const data=await request("/api/system");
      state.system=data;
      text("sourceLines",number(data.total.lines));
      text("sourceFiles",number(data.total.files));
      $("statusIndicator").innerHTML="<i></i> PyBot取得済み";
      view("system");
      status("PyBotの固定コミットから "+number(data.total.files)+"ファイルをASTで解析しました。");
    }catch(error){toastError(error);$("statusIndicator").textContent="読込失敗";}
  }
  function setupGraphControls(){
    const graph=$("network");
    graph.addEventListener("wheel",event=>{
      event.preventDefault();
      const rect=graph.getBoundingClientRect();
      const x=(event.clientX-rect.left)/rect.width*1140;
      const y=(event.clientY-rect.top)/rect.height*640;
      cameraZoom(event.deltaY<0?1.12:.89,x,y);
    },{passive:false});
    graph.addEventListener("pointerdown",event=>{
      if(event.button!==0)return;
      if(event.target.closest(".graph-node"))return;
      state.drag={x:event.clientX,y:event.clientY,ox:state.offsetX,oy:state.offsetY};
      graph.setPointerCapture(event.pointerId);
    });
    graph.addEventListener("pointermove",event=>{
      if(!state.drag)return;
      const rect=graph.getBoundingClientRect();
      state.offsetX=state.drag.ox+(event.clientX-state.drag.x)*1140/rect.width;
      state.offsetY=state.drag.oy+(event.clientY-state.drag.y)*640/rect.height;
      moveCamera();
    });
    for(const event of ["pointerup","pointercancel","lostpointercapture"])
      graph.addEventListener(event,()=>{state.drag=null;});
    $("zoomIn").onclick=()=>cameraZoom(1.23);
    $("zoomOut").onclick=()=>cameraZoom(.81);
    $("zoomReset").onclick=cameraReset;
    $("graphExpand").onclick=()=>{
      state.expanded=!state.expanded;
      document.body.classList.toggle("expanded-map",state.expanded);
      $("graphExpand").textContent=state.expanded?"⤡ 戻す":"⤢";
    };
    document.addEventListener("keydown",e=>{
      if(e.key==="Escape"&&state.expanded){
        state.expanded=false;document.body.classList.remove("expanded-map");$("graphExpand").textContent="⤢";
      }
    });
  }
  function setupThemeAndFonts(){
    let saved=null;
    try{saved=localStorage.getItem("pybot-network-theme");}catch(_){}
    state.theme=saved==="light"||saved==="dark"?saved:
      (window.matchMedia&&window.matchMedia("(prefers-color-scheme:light)").matches?"light":"dark");
    function applyTheme(){
      document.documentElement.dataset.theme=state.theme;
      document.documentElement.style.colorScheme=state.theme;
      $("themeButton").textContent=state.theme==="light"?"☾ ダークへ":"☀ ライトへ";
      if(state.system)renderGraph();
    }
    $("themeButton").onclick=()=>{
      state.theme=state.theme==="light"?"dark":"light";
      try{localStorage.setItem("pybot-network-theme",state.theme);}catch(_){}
      applyTheme();
    };
    applyTheme();
    let n=1;
    try{const value=Number(localStorage.getItem("pybot-network-font"));if(value>=1&&value<=1.75)n=value;}catch(_){}
    function font(){
      state.font=n;document.documentElement.style.setProperty("--font",n);
      text("fontPercent",Math.round(n*100)+"%");
      try{localStorage.setItem("pybot-network-font",String(n));}catch(_){}
    }
    $("fontDown").onclick=()=>{n=Math.max(1,n-.25);font();};
    $("fontUp").onclick=()=>{n=Math.min(1.75,n+.25);font();};
    font();
  }
  function init(){
    setupThemeAndFonts();setupGraphControls();
    document.querySelectorAll("[data-example]").forEach(b=>b.onclick=()=>{
      $("questionInput").value=b.dataset.example;$("questionInput").focus();
      document.querySelectorAll("[data-example]").forEach(x=>x.classList.toggle("active",x===b));
    });
    document.querySelectorAll("[data-mode]").forEach(b=>b.onclick=()=>view(b.dataset.mode));
    $("density").oninput=value=>{
      state.density=Number(value.target.value);
      text("densityLabel",state.density);renderGraph();
    };
    $("sendQuestion").onclick=ask;
    $("questionInput").onkeydown=e=>{
      if(e.key==="Enter"&&!e.shiftKey&&!e.isComposing){e.preventDefault();ask();}
    };
    $("visualize").onclick=analyze;
    $("clearChat").onclick=async()=>{
      if(state.busy)return;
      if(state.turns.length&&!confirm("この会話と解析結果をリセットしますか？"))return;
      try{
        if(state.turns.length)await request("/api/reset",{session:state.session});
        pause();state.turns=[];state.turnIndex=-1;state.trace=null;state.selected=null;
        $("candidates").innerHTML='<span class="muted">質問すると候補を表示します。</span>';
        text("candidateMeta","—");$("visualize").disabled=true;
        renderChat();view("system");toast("会話と解析結果をリセットしました");
      }catch(error){toastError(error);}
    };
    $("play").onclick=playback;
    $("goFirst").onclick=()=>{pause();frameAt(0);};
    $("goBack").onclick=()=>{pause();frameAt(state.activeFrame-1);};
    $("goNext").onclick=()=>{pause();frameAt(state.activeFrame+1);};
    $("goLast").onclick=()=>{pause();frameAt(state.trace.frames.length-1);};
    $("timeline").oninput=e=>{pause();frameAt(Number(e.target.value));};
    $("speed").onclick=()=>{
      state.speed=state.speed===1?2:state.speed===2?4:state.speed===4?.5:1;
      $("speed").textContent="×"+state.speed;
      if(state.playing!==null){pause();playback();}
    };
    loadSystem();
  }
  document.addEventListener("DOMContentLoaded",init);
})();