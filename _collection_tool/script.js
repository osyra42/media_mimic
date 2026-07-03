let newLineCount = 0;

const STORAGE_KEY = "collection-tool-data";
const dots = ["\u{1F7E3}", "\u{1F7E2}", "\u{1F7E1}", "\u{1F534}", "\u{1F535}"];
const NONE_FLAG = "\u{2B1B}";
const flags = [NONE_FLAG, "\u{2B50}", "\u{26A0}\u{FE0F}"];
const TITLE_PAD_WIDTH = 50;
const SYNC_DEBOUNCE_MS = 500;

let textareaTimer = null;

document.addEventListener("DOMContentLoaded", () => {
  const inputEl = document.getElementById("input");
  const formEl = document.getElementById("form");

  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved) inputEl.value = saved;

  inputEl.addEventListener("input", () => {
    localStorage.setItem(STORAGE_KEY, inputEl.value);
    updateCounts();
    scheduleAutoIterate();
  });

  formEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      convert();
      iterate();
    }
  });

  formEl.addEventListener("change", (e) => {
    if (e.target.type === "radio") convert();
  });

  iterate();
  updateCounts();
});

function scheduleAutoIterate() {
  clearTimeout(textareaTimer);
  textareaTimer = setTimeout(() => {
    if (document.activeElement && document.activeElement.closest("#form")) return;
    iterate();
  }, SYNC_DEBOUNCE_MS);
}

function clearData() {
  localStorage.removeItem(STORAGE_KEY);
  document.getElementById("input").value = "";
  document.getElementById("form").innerHTML = "";
  updateCounts();
}

function updateCounts() {
  const text = document.getElementById("input").value;
  const counts = {};
  dots.forEach((d) => (counts[d] = 0));
  text.split("\n").forEach((line) => {
    const parsed = parseLine(line);
    if (parsed) counts[parsed.dot]++;
  });

  const el = document.getElementById("status-counts");
  if (!el) return;
  el.innerHTML = "";
  dots.forEach((dot, i) => {
    if (i > 0) {
      const sep = document.createElement("span");
      sep.className = "status-sep";
      sep.textContent = "·";
      el.appendChild(sep);
    }
    const item = document.createElement("span");
    item.className = "status-count";
    item.textContent = `${dot} ${counts[dot]}`;
    el.appendChild(item);
  });
}

function imdbSearchUrl(title) {
  const params = new URLSearchParams({ q: title });
  return `https://www.imdb.com/find/?${params.toString()}`;
}

function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text);
    return;
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  ta.remove();
}

function parseLine(line) {
  let flag = NONE_FLAG;
  let remaining = line;

  // Check for emoji flags at start of line
  for (const f of flags) {
    if (f !== NONE_FLAG && remaining.startsWith(f)) {
      flag = f;
      remaining = remaining.slice(f.length);
      break;
    }
  }

  // Strip none-flag prefix if present
  if (flag === NONE_FLAG) {
    for (const prefix of [NONE_FLAG, "\u{3000}\u{2009}", "\u{3000}", "  "]) {
      if (remaining.startsWith(prefix)) {
        remaining = remaining.slice(prefix.length);
        break;
      }
    }
  }

  // Find dot
  const dot = dots.find((d) => remaining.startsWith(d));
  if (!dot) return null;

  const rest = remaining.slice(dot.length).trim();
  const sepIndex = rest.lastIndexOf(" | ");
  let text = rest;
  let extra = "";
  if (sepIndex !== -1) {
    text = rest.slice(0, sepIndex).trim();
    extra = rest.slice(sepIndex + 3).trim();
  }
  return { flag, dot, text, extra };
}

function iterate() {
  const formElement = document.getElementById("form");
  formElement.innerHTML = "";

  const inputElement = document.getElementById("input");
  const inputLines = inputElement.value.split("\n");

  const parsedLines = inputLines.map(parseLine).filter(Boolean);

  // Group lines by dot
  const groupedLines = {};
  parsedLines.forEach((parsed) => {
    if (!groupedLines[parsed.dot]) {
      groupedLines[parsed.dot] = [];
    }
    groupedLines[parsed.dot].push(parsed);
  });

  // Sort each group alphabetically by text
  Object.keys(groupedLines).forEach((dot) => {
    groupedLines[dot].sort((a, b) => a.text.localeCompare(b.text));
  });

  // Reconstruct sorted lines
  const sortedLines = [];
  dots.forEach((dot) => {
    if (groupedLines[dot]) {
      sortedLines.push(...groupedLines[dot]);
    }
  });

  // Display
  sortedLines.forEach((parsed, index) => {
    const dotGroup = createDotGroup(index, parsed);
    formElement.appendChild(dotGroup);
  });
}

function addNewLine() {
  const formElement = document.getElementById("form");
  const parsed = { flag: NONE_FLAG, dot: "\u{1F535}", text: "", extra: "" };
  const dotGroup = createDotGroup(newLineCount, parsed, true);
  formElement.insertBefore(dotGroup, formElement.firstChild);
  newLineCount++;
}

function createDotGroup(index, parsed, isNew = false) {
  const dotGroup = document.createElement("div");
  dotGroup.className = "dot-group";

  const prefix = isNew ? "new" : "iterated";

  // Flag radio buttons
  const flagName = `flag-${prefix}-${index}`;
  flags.forEach((flag) => {
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = flagName;
    radio.id = `radio-flag-${prefix}-${index}-${flag}`;
    radio.value = flag;
    radio.className = "flag-radio";
    if (flag === parsed.flag) radio.checked = true;

    const label = document.createElement("label");
    label.htmlFor = radio.id;
    label.textContent = flag === NONE_FLAG ? "\u{00B7}" : flag;
    if (flag === NONE_FLAG) label.classList.add("flag-none-label");

    dotGroup.appendChild(radio);
    dotGroup.appendChild(label);
  });

  // Separator between flags and dots
  const sep = document.createElement("span");
  sep.className = "flag-dot-separator";
  sep.textContent = "\u{2502}";
  dotGroup.appendChild(sep);

  // Dot radio buttons
  const dotName = `option-${prefix}-${index}`;
  dots.forEach((dot) => {
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = dotName;
    radio.id = `radio-${prefix}-${index}-${dot}`;
    radio.value = dot;
    if (dot === parsed.dot) radio.checked = true;

    const label = document.createElement("label");
    label.htmlFor = radio.id;
    label.textContent = dot;

    dotGroup.appendChild(radio);
    dotGroup.appendChild(label);
  });

  // Text content
  const textElement = isNew ? document.createElement("input") : document.createElement("span");
  textElement.className = "dot-group-text";
  if (isNew) {
    textElement.type = "text";
    textElement.placeholder = "Enter text here";
  } else {
    textElement.textContent = parsed.text;
  }
  dotGroup.appendChild(textElement);

  // Extra (seasons/episodes/movie id)
  const extraElement = isNew ? document.createElement("input") : document.createElement("span");
  extraElement.className = "dot-group-extra";
  if (isNew) {
    extraElement.type = "text";
    extraElement.placeholder = "s00e00";
  } else {
    extraElement.textContent = parsed.extra || "";
  }
  dotGroup.appendChild(extraElement);

  // Row actions (only for iterated rows)
  if (!isNew) {
    const actions = document.createElement("div");
    actions.className = "row-actions";

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "row-action row-action-delete";
    delBtn.textContent = "\u{274C}";
    delBtn.title = "Delete";
    delBtn.onclick = () => {
      dotGroup.remove();
      convert();
    };
    actions.appendChild(delBtn);

    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "row-action";
    copyBtn.textContent = "\u{1F4CB}";
    copyBtn.title = "Copy title";
    copyBtn.onclick = () => copyText(parsed.text);
    actions.appendChild(copyBtn);

    const linkBtn = document.createElement("a");
    linkBtn.className = "row-action";
    linkBtn.textContent = "\u{1F517}";
    linkBtn.title = "Search IMDB";
    linkBtn.href = imdbSearchUrl(parsed.text);
    linkBtn.target = "_blank";
    linkBtn.rel = "noopener noreferrer";
    actions.appendChild(linkBtn);

    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "row-action";
    editBtn.textContent = "\u{270F}\u{FE0F}";
    editBtn.title = "Edit";
    editBtn.onclick = () => makeEditable(dotGroup);
    actions.appendChild(editBtn);

    dotGroup.appendChild(actions);
  }

  return dotGroup;
}

function makeEditable(dotGroup) {
  const textSpan = dotGroup.querySelector("span.dot-group-text");
  const extraSpan = dotGroup.querySelector("span.dot-group-extra");

  [textSpan, extraSpan].forEach((span) => {
    if (!span) return;
    const input = document.createElement("input");
    input.type = "text";
    input.className = span.className;
    input.value = span.textContent;
    if (span.classList.contains("dot-group-extra")) input.placeholder = "s00e00";
    span.replaceWith(input);
  });

  const actions = dotGroup.querySelector(".row-actions");
  if (actions) actions.remove();
}

function convert() {
  const formElement = document.getElementById("form");
  const outputElement = document.getElementById("input");
  const dotGroups = Array.from(formElement.querySelectorAll(".dot-group"));

  // Sort by dot color order
  dotGroups.sort((a, b) => {
    const aRadio = a.querySelector("input[type='radio']:not(.flag-radio):checked");
    const bRadio = b.querySelector("input[type='radio']:not(.flag-radio):checked");
    const aIndex = dots.indexOf(aRadio.value);
    const bIndex = dots.indexOf(bRadio.value);
    return aIndex - bIndex;
  });

  let outputText = "";

  dotGroups.forEach((group) => {
    const flagRadio = group.querySelector(".flag-radio:checked");
    const dotRadio = group.querySelector("input[type='radio']:not(.flag-radio):checked");
    const textElement = group.querySelector(".dot-group-text");
    const extraElement = group.querySelector(".dot-group-extra");
    const text = textElement ? (textElement.value || textElement.textContent).trim() : "";
    const extra = extraElement ? (extraElement.value || extraElement.textContent).trim() : "";

    if (dotRadio && text) {
      const flag = flagRadio ? flagRadio.value : NONE_FLAG;
      const body = extra ? text.padEnd(TITLE_PAD_WIDTH) + " | " + extra : text;
      outputText += flag + dotRadio.value + " " + body + "\n";
    }
  });

  outputElement.value = `\`\`\`\n${outputText}\`\`\``;
  localStorage.setItem(STORAGE_KEY, outputElement.value);
  updateCounts();
}

function copy() {
  const outputElement = document.getElementById("input");
  outputElement.select();
  document.execCommand("copy");
}
