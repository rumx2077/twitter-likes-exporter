(function () {
  const overlay = document.createElement('div');
  overlay.className = 'lb';
  overlay.hidden = true;
  overlay.innerHTML = `
    <div class="lb-stage">
      <img class="lb-img" draggable="false">
    </div>
    <button class="lb-prev" aria-label="Prev">‹</button>
    <button class="lb-next" aria-label="Next">›</button>
    <button class="lb-close" aria-label="Close">×</button>
  `;
  document.addEventListener('click', onThumbClick);
  document.body.appendChild(overlay);

  let group = [];
  let idx = 0;
  let scale = 1;
  let startScale = 1;
  let startDist = 0;
  let wheelLock = 0;
  let touchStart = null;
  let tx = 0;
  let ty = 0;
  let panStart = null;
  let basePct = 100;
  let cycleList = [];
  let cycleIndex = 0;

  const img = overlay.querySelector('.lb-img');
  const stage = overlay.querySelector('.lb-stage');

  function show(items, i) {
    group = items;
    idx = i;
    overlay.hidden = false;
    fitVV();
    render();
    bind(true);
  }

  function hide() {
    overlay.hidden = true;
    bind(false);
    resetTransform();
  }

  function render() {
    img.style.width = '';
    img.style.maxHeight = '';
    img.src = group[idx];
    overlay.classList.toggle('single', group.length <= 1);
    overlay.classList.remove('top');
    // 避免上次的滚动位置残留
    try { stage.scrollTop = 0; stage.scrollLeft = 0; } catch (e) {}
    img.onload = () => {
      // 计算原始宽度百分比并生成循环序列（原图 -> 大于原图的级别）
      const w = img.clientWidth || 0;
      const sw = stage.clientWidth || 1;
      basePct = Math.round((w / sw) * 100);
      const levels = [50, 75, 100];
      const bigger = levels.filter(v => v > basePct);
      cycleList = [basePct, ...bigger];
      cycleIndex = 0;
    };
  }

  function prev() {
    if (group.length > 1) {
      idx = (idx - 1 + group.length) % group.length;
      resetTransform();
      render();
    }
  }

  function next() {
    if (group.length > 1) {
      idx = (idx + 1) % group.length;
      resetTransform();
      render();
    }
  }

  function applyTransform() {
    img.style.transform = `translate(${tx}px,${ty}px) scale(${scale})`;
  }

  function clamp() {
    const w = stage.clientWidth;
    const h = stage.clientHeight;
    const iw = img.naturalWidth * scale;
    const ih = img.naturalHeight * scale;
    const maxX = Math.max(0, (iw - w) / 2) / scale;
    const maxY = Math.max(0, (ih - h) / 2) / scale;
    tx = Math.max(-maxX, Math.min(maxX, tx));
    ty = Math.max(-maxY, Math.min(maxY, ty));
  }

  function resetTransform() {
    scale = 1;
    tx = 0;
    ty = 0;
    applyTransform();
  }

  overlay.addEventListener('click', (e) => {
    // 遮罩层内点击不向外冒泡，避免影响页面其他元素
    e.stopPropagation();
    if (e.target.closest('.lb-prev')) {
      prev();
      return;
    }
    if (e.target.closest('.lb-next')) {
      next();
      return;
    }
    if (e.target.closest('.lb-close')) {
      hide();
      return;
    }
    if (!e.target.closest('.lb-img')) hide();
  });

  // 遮罩层拦截常见事件，防止冒泡到页面
  ['wheel','mousedown','mouseup','touchstart','touchmove','touchend','contextmenu'].forEach((type) => {
    overlay.addEventListener(type, (e) => { e.stopPropagation(); }, { passive: true });
  });

  function bind(on) {
    const fn = on ? 'addEventListener' : 'removeEventListener';
    window[fn]('keydown', onKey);
    window[fn]('wheel', onWheel, { passive: false });
    if (window.visualViewport) {
      visualViewport[fn]('resize', fitVV);
      visualViewport[fn]('scroll', fitVV);
    }
    stage[fn]('touchstart', onTouch, { passive: false });
    stage[fn]('touchmove', onTouchMove, { passive: false });
    stage[fn]('touchend', onTouchEnd);
  }

  function onKey(e) {
    if (overlay.hidden) return;
    if (e.key === 'Escape') hide();
    else if (e.key === 'ArrowLeft') prev();
    else if (e.key === 'ArrowRight') next();
  }

  function onWheel(e) {
    if (overlay.hidden) return;
    // 顶部对齐模式：允许默认滚动（由 CSS overflow 生效）
    if (overlay.classList.contains('top')) return;
    // 非顶部模式仍用于切换图片
    e.preventDefault();
    const t = Date.now();
    if (t - wheelLock < 200) return;
    wheelLock = t;
    (e.deltaY > 0 ? next : prev)();
  }

  function dist(t) {
    const dx = t[0].clientX - t[1].clientX;
    const dy = t[0].clientY - t[1].clientY;
    return Math.hypot(dx, dy);
  }

  function onTouch(e) {
    if (e.touches.length === 2) {
      e.preventDefault();
      startDist = dist(e.touches);
      startScale = scale;
    } else if (e.touches.length === 1) {
      // 在顶部对齐模式下（单击放大），允许原生滚动，不进行自定义手势
      if (overlay.classList.contains('top')) {
        touchStart = null;
        panStart = null;
        return;
      }
      const p = {
        x: e.touches[0].clientX,
        y: e.touches[0].clientY,
        t: Date.now(),
      };
      if (scale > 1) {
        panStart = { x: p.x, y: p.y, tx, ty };
      } else {
        touchStart = p;
      }
    }
  }

  function onTouchMove(e) {
    if (e.touches.length === 2) {
      e.preventDefault();
      const s = (dist(e.touches) / startDist) * startScale;
      scale = Math.max(1, Math.min(5, s));
      clamp();
      applyTransform();
    } else if (e.touches.length === 1) {
      // 顶部对齐模式允许原生滚动，不拦截
      if (overlay.classList.contains('top')) return;
      e.preventDefault();
      if (scale > 1 && panStart) {
        const p = e.touches[0];
        tx = panStart.tx + (p.clientX - panStart.x) / scale;
        ty = panStart.ty + (p.clientY - panStart.y) / scale;
        clamp();
        applyTransform();
      }
    }
  }

  function onTouchEnd(e) {
    // 顶部对齐模式下，不进行快滑切换/上滑关闭的手势判断
    if (overlay.classList.contains('top')) {
      touchStart = null;
      panStart = null;
      return;
    }
    if (touchStart && e.changedTouches.length) {
      const dx = e.changedTouches[0].clientX - touchStart.x;
      const dy = e.changedTouches[0].clientY - touchStart.y;
      const dt = Date.now() - touchStart.t;
      if (dt < 400 && Math.abs(dx) > 50 && Math.abs(dy) < 80)
        (dx < 0 ? next : prev)();
      else if (dt < 400 && dy < -80) hide();
    }
    touchStart = null;
    panStart = null;
  }

  function fitVV() {
    const vv = window.visualViewport;
    if (vv) {
      overlay.style.width = vv.width + 'px';
      overlay.style.height = vv.height + 'px';
      overlay.style.transform = `translate(${vv.offsetLeft}px,${vv.offsetTop}px)`;
      overlay.style.setProperty('--ui', 1 / (vv.scale || 1));
    } else {
      overlay.style.width = '100vw';
      overlay.style.height = '100vh';
      overlay.style.transform = 'translate(0,0)';
    }
  }

  function onThumbClick(e) {
    const imgEl = e.target && e.target.closest('.tweet_images_wrapper img');
    if (!imgEl) return;
    e.preventDefault();
    e.stopPropagation();
    const wrapper = imgEl.closest('.tweet_images_wrapper');
    const items = Array.from(wrapper.querySelectorAll('img')).map((i) => i.src);
    const i = items.indexOf(imgEl.src);
    show(items, i);
  }

  // 点击图片时按 原图 -> 50%/75%/100%（仅选择大于原图的级别）循环
  img.addEventListener('click', (e) => {
    e.stopPropagation();
    if (!cycleList || cycleList.length <= 1) return; // 原图就是100%时不处理
    cycleIndex = (cycleIndex + 1) % cycleList.length;
    if (cycleIndex === 0) {
      img.style.width = '';
      img.style.maxHeight = '';
      overlay.classList.remove('top');
      try { stage.scrollTop = 0; stage.scrollLeft = 0; } catch (e) {}
    } else {
      img.style.width = cycleList[cycleIndex] + '%';
      // 单击时去除 max-height，并使图片顶部对齐
      img.style.maxHeight = 'none';
      overlay.classList.add('top');
      // 进入顶部对齐模式时，强制滚动到顶部/最左
      try { stage.scrollTop = 0; stage.scrollLeft = 0; } catch (e) {}
    }
    resetTransform();
  });
})();
