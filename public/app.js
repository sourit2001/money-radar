const state = {
  posts: [],
  meta: { total: 0, channels: [], subreddits: [] },
};

const els = {
  posts: document.querySelector("#posts"),
  summary: document.querySelector("#summary"),
  refresh: document.querySelector("#refresh"),
  channel: document.querySelector("#channel"),
  subreddit: document.querySelector("#subreddit"),
  minScore: document.querySelector("#min-score"),
  scoreLabel: document.querySelector("#score-label"),
  search: document.querySelector("#search"),
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[char]);
}

function formatDate(seconds) {
  if (!seconds) return "unknown date";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
    .format(new Date(seconds * 1000));
}

function fillSelect(select, values, firstLabel) {
  const current = select.value;
  select.innerHTML = `<option value="">${firstLabel}</option>`;
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
  select.value = values.includes(current) ? current : "";
}

function queryString() {
  const params = new URLSearchParams();
  if (els.channel.value) params.set("channel", els.channel.value);
  if (els.subreddit.value) params.set("subreddit", els.subreddit.value);
  if (els.search.value.trim()) params.set("search", els.search.value.trim());
  params.set("min_score", els.minScore.value);
  return params.toString();
}

async function loadPosts() {
  els.summary.textContent = "Loading Reddit opportunity posts...";
  const response = await fetch(`/api/posts?${queryString()}`);
  if (!response.ok) {
    els.summary.textContent = "Could not load posts from the local API.";
    return;
  }
  const payload = await response.json();
  state.posts = payload.posts;
  state.meta = payload.meta;
  fillSelect(els.channel, state.meta.channels, "All channels");
  fillSelect(els.subreddit, state.meta.subreddits, "All subreddits");
  render();
}

function render() {
  els.scoreLabel.textContent = `${els.minScore.value}+`;
  els.summary.textContent = `${state.posts.length} shown from ${state.meta.total} saved posts`;
  if (!state.posts.length) {
    els.posts.innerHTML = `<div class="empty">No matching posts yet. Try lowering the score filter or running the sample/fetch command.</div>`;
    return;
  }
  els.posts.innerHTML = state.posts.map((post) => `
    <article class="post">
      <div class="post-header">
        <h2><a href="${escapeHtml(post.permalink)}" target="_blank" rel="noreferrer">${escapeHtml(post.title)}</a></h2>
        <div class="score">${escapeHtml(post.value_score)}/5</div>
      </div>
      <div class="meta">
        <span>r/${escapeHtml(post.subreddit)}</span>
        <span>${escapeHtml(post.channel)}</span>
        <span>${escapeHtml(post.score)} upvotes</span>
        <span>${escapeHtml(post.num_comments)} comments</span>
        <span>${formatDate(post.created_utc)}</span>
      </div>
      <p class="excerpt">${escapeHtml(post.selftext || post.pain_summary)}</p>
      <div class="annotation">
        <div><strong>Pain:</strong> ${escapeHtml(post.pain_summary)}</div>
        <div class="tags">
          <span class="tag">${escapeHtml(post.signal)}</span>
          <span class="tag">${escapeHtml(post.opportunity_type)}</span>
          ${post.signal_phrase ? `<span class="tag">${escapeHtml(post.signal_phrase)}</span>` : ""}
        </div>
      </div>
    </article>
  `).join("");
}

["change", "input"].forEach((eventName) => {
  els.channel.addEventListener(eventName, loadPosts);
  els.subreddit.addEventListener(eventName, loadPosts);
  els.minScore.addEventListener(eventName, loadPosts);
  els.search.addEventListener(eventName, () => {
    window.clearTimeout(els.search._timer);
    els.search._timer = window.setTimeout(loadPosts, 180);
  });
});

els.refresh.addEventListener("click", loadPosts);
loadPosts();

