import cytoscape from 'cytoscape';
import './style.css';

const byId = (id) => document.getElementById(id);
const maxBytes = 25 * 1024 * 1024;
const predictedMethods = new Set(['tfidf_cosine', 'lexical']);
let imported = null;
let highlightedId = '';

const graph = cytoscape({
  container: byId('graph'),
  elements: [],
  style: [
    { selector: 'node', style: {
      'label': 'data(label)', 'font-size': 11, 'font-family': 'system-ui, sans-serif',
      'text-outline-width': 2, 'text-outline-color': '#0d1727', 'color': '#e7ebf3',
      'text-wrap': 'ellipsis', 'text-max-width': '120px',
      'background-color': '#7b91b3', 'width': 22, 'height': 22, 'border-width': 1,
      'border-color': '#a7b4ca'
    }},
    { selector: 'node[kind = "专利文献"]', style: {'background-color': '#60a5fa','width': 29,'height': 29}},
    { selector: 'node[kind = "论文文献"]', style: {'background-color': '#4ade80','width': 27,'height': 27}},
    { selector: 'node[kind = "发明候选"]', style: {'background-color': '#fbbf24','width': 34,'height': 34}},
    { selector: 'node[kind = "候选词项"]', style: {'background-color': '#7d86a8','width': 13,'height': 13,'font-size': 9}},
    { selector: 'node[kind = "公开项目"]', style: {'background-color': '#c084fc','width': 36,'height': 36}},
    { selector: 'edge', style: {'width': 1.4,'line-color': '#64748b', 'curve-style': 'bezier',
      'target-arrow-shape': 'triangle', 'target-arrow-color': '#64748b',
      'arrow-scale': 0.65,'opacity': 0.65}},
    { selector: 'edge[method = "tfidf_cosine"]', style: {
      'line-style': 'dashed','line-color': '#d4a451', 'target-arrow-shape': 'none', 'width': 1.2
    }},
    { selector: 'node:selected', style: {'border-color': '#ffffff','border-width': 3}},
    { selector: '.dimmed', style: {'opacity': 0.13}},
    { selector: '.invisible', style: {'display': 'none'}}
  ],
  layout: {name: 'grid'}, minZoom: 0.12, maxZoom: 4,
});

function repaint() {
  const threshold = Number(byId('threshold').value);
  const search = byId('search').value.trim().toLowerCase();
  const showTerms = byId('show-terms').checked;
  const showPredicted = byId('show-predicted').checked;
  byId('threshold-value').value = threshold.toFixed(2);
  graph.batch(() => {
    graph.nodes().forEach((node) => {
      const kind = String(node.data('kind') || '');
      const label = String(node.data('label') || '');
      const key = String(node.data('id') || '');
      const hide = !showTerms && kind !== '专利文献' && kind !== '论文文献'
        && kind !== '公开项目' && kind !== '发明候选';
      node.toggleClass('invisible', hide);
      node.toggleClass('dimmed', Boolean(search && !(label + ' ' + key).toLowerCase().includes(search)));
    });
    graph.edges().forEach((edge) => {
      const method = String(edge.data('method') || '');
      const score = edge.data('score');
      const hide = edge.source().hasClass('invisible') || edge.target().hasClass('invisible') ||
        (!showPredicted && predictedMethods.has(method)) ||
        (score !== null && score !== undefined && Number(score) < threshold);
      edge.toggleClass('invisible', hide);
      edge.toggleClass('dimmed', Boolean(search && edge.source().hasClass('dimmed')
        && edge.target().hasClass('dimmed')));
    });
  });
}

function layout() {
  const count = graph.nodes().length;
  if (!count) return;
  graph.layout({
    name: count <= 200 ? 'cose' : 'grid',
    animate: false, fit: true, padding: 40,
    nodeRepulsion: () => 380000,
    idealEdgeLength: () => 95,
    randomize: true,
  }).run();
}

function setDetail(node) {
  highlightedId = node.id();
  const detail = byId('detail');
  detail.replaceChildren();
  const values = {
    '名称': node.data('label'),
    '节点类型': node.data('kind'),
    '证据编号': node.id(),
    '公开号 / DOI': node.data('publication'),
    '来源': node.data('source'),
    '验证状态': node.data('verified') === true ? '已标记核验' :
      (node.data('verified') === false ? '待核验' : '无核验状态'),
  };
  for (const [label, raw] of Object.entries(values)) {
    if (raw === undefined || raw === '') continue;
    const item = document.createElement('div');
    item.className = 'detail-field';
    const caption = document.createElement('b');
    caption.textContent = label + '：';
    const value = document.createElement('span');
    value.textContent = String(raw);
    item.append(caption, value);
    detail.append(item);
  }
  const source = String(node.data('url') || '');
  if (source.startsWith('https://')) {
    const link = document.createElement('a');
    link.href = source; link.target = '_blank'; link.rel = 'noopener noreferrer';
    link.textContent = '查看原始公开地址';
    detail.append(link);
  }
  const neighborhood = graph.edges().filter((edge) =>
    edge.source().id() === highlightedId || edge.target().id() === highlightedId);
  const summary = document.createElement('p');
  summary.textContent = '可查看直接关联关系：' + neighborhood.length + ' 条。'
    + ' 关系含义必须结合文献原文和证据字段复核。';
  detail.append(summary);
}

function loadData(data, filename) {
  if (!data || typeof data !== 'object' ||
      !Array.isArray(data.elements?.nodes) || !Array.isArray(data.elements?.edges)) {
    throw new Error('缺少 elements.nodes / elements.edges；请选择 atlas-export 生成的 JSON。');
  }
  if (data.elements.nodes.length > 1000 || data.elements.edges.length > 12000) {
    throw new Error('图谱超过交互预算。请在 atlas-export 缩小 max-nodes 或过滤边。');
  }
  const seen = new Set();
  const nodes = data.elements.nodes.map((n) => {
    if (!n || typeof n.data?.id !== 'string' || seen.has(n.data.id)) {
      throw new Error('存在重复/非法节点 ID。');
    }
    seen.add(n.data.id);
    return {data: {...n.data, label: String(n.data.label || n.data.id).slice(0, 300)}};
  });
  const edges = data.elements.edges.filter((e) => e && seen.has(e.data?.source) &&
    seen.has(e.data?.target)).map((e) => ({data: e.data}));
  imported = {scope: data.scope, nodes: nodes.length, edges: edges.length};
  graph.elements().remove();
  graph.add([...nodes, ...edges]);
  layout();
  repaint();
  byId('file-status').textContent = '已导入：' + filename + '｜' +
    (data.scope || '未注明范围') + '｜原始索引：' + (data.index_digest || '无');
  byId('graph-count').textContent = nodes.length + ' 个节点 / ' + edges.length +
    ' 条关系' + (data.truncated ? '（已截断以保证可读性）' : '');
}

byId('graph-file').addEventListener('change', async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  if (file.size > maxBytes) {
    byId('file-status').textContent = '导入失败：单文件不能超过 25MB。';
    return;
  }
  try {
    loadData(JSON.parse(await file.text()), file.name);
  } catch (error) {
    byId('file-status').textContent = '导入失败：' + String(error.message || error);
  }
});
for (const id of ['search', 'threshold', 'show-terms', 'show-predicted']) {
  byId(id).addEventListener('input', repaint);
}
byId('fit').addEventListener('click', () => graph.fit(graph.elements(':visible'), 32));
byId('layout').addEventListener('click', layout);
graph.on('tap', 'node', (event) => setDetail(event.target));
