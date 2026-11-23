import re
import shutil
import subprocess
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "static/js/index.js"


@unittest.skipUnless(shutil.which("node"), "Node.js required")
class GradingProgressTests(unittest.TestCase):
    def test_duplicate_start_configuration_failure_and_terminal_error_states(self):
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        functions = []
        for name in ("runPregrader", "updateRunButton", "finalizeProgress"):
            match = re.search(
                rf"(?:async )?function {name}\([^)]*\) \{{.*?^\}}",
                source, re.DOTALL | re.MULTILINE,
            )
            self.assertIsNotNone(match)
            functions.append(match.group(0))
        script = """
const assert = require('node:assert/strict');
const elements = new Map();
function element() {
  const classes = new Set();
  return {
    style: {}, value: '', textContent: '', innerHTML: '', dataset: {}, disabled: false,
    classList: {
      add: v => classes.add(v), remove: (...vs) => vs.forEach(v => classes.delete(v)),
      contains: v => classes.has(v),
      toggle: (v, on) => on ? classes.add(v) : classes.delete(v),
    },
    setAttribute() {}, scrollIntoView() {},
  };
}
let pending = [];
const document = {
  getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
  querySelector() { return element(); },
  querySelectorAll() { return pending; },
};
let gradingInProgress = false, currentJobId = null, _gradingStartedAt = 0;
let _files = { zip: {}, pdf: [{}] }, enunciadoMode = 'pdf';
let liveResults = [], totalStudents = 0, completedStudents = 0;
let logVisible = false, activeFilters = new Set(), currentSort = '', studentSearchQuery = '';
let resolveConfig, saveCalls = 0, runCalls = 0;
let statusBadge, statusDot;
const toasts = [];
const UI = { toast: (text, options) => toasts.push({text, ...options}) };
function saveConfig() { saveCalls++; return new Promise(resolve => { resolveConfig = resolve; }); }
function setRunning(running) { gradingInProgress = running; updateRunButton(); }
function setStatusDot(value) { statusDot = value; }
function setStatusBadge(value) { statusBadge = value; }
function setStatusText() {}
function appendLog() {}
function appendPregraderFiles() {}
function flashZone() { throw new Error('Unexpected missing upload'); }
function showResultsCard() {}
function esc(s) { return s; }
function truncName(s) { return s; }
const fetch = async () => { runCalls++; return {ok:true, json:async () => ({job_id:'one'})}; };
let stream;
class EventSource {
  constructor() { stream = this; }
  close() {}
}
"""
        script += "\n".join(functions)
        script += """
(async () => {
  const first = runPregrader();
  await runPregrader();
  updateRunButton();
  assert.equal(saveCalls, 1);
  assert.equal(document.getElementById('btn-run').disabled, true);
  assert.equal(runCalls, 0);
  resolveConfig(true);
  await first;
  assert.equal(runCalls, 1);
  await runPregrader();
  assert.equal(runCalls, 1);

  liveResults = [{estado:'evaluado'}, {estado:'error'}];
  totalStudents = 2; completedStudents = 2;
  await stream.onmessage({data:JSON.stringify({type:'done', count:2, failed:1})});
  assert.equal(statusBadge, 'Requiere revisión');
  assert.equal(statusDot, 'error');
  assert.equal(gradingInProgress, false);

  const failedSave = runPregrader();
  resolveConfig(false);
  await failedSave;
  assert.equal(gradingInProgress, false);
  assert.equal(runCalls, 1);

  const retry = runPregrader();
  resolveConfig(true);
  await retry;
  pending = [{dataset:{name:'Pending'}, className:'chip pending'}];
  totalStudents = 2; completedStudents = 1;
  await stream.onmessage({data:JSON.stringify({type:'error', data:'Process failed'})});
  assert.equal(pending[0].className, 'chip grade-na');
  assert.match(pending[0].innerHTML, /Sin resultado/);
  assert.equal(document.getElementById('live-prog-text').textContent, '1 de 2 entregas procesadas');
  assert.equal(gradingInProgress, false);
})().catch(error => { console.error(error); process.exit(1); });
"""
        subprocess.run(["node", "-e", script], check=True, timeout=15)


if __name__ == "__main__":
    unittest.main()
