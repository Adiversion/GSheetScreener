/**
 * test_research_engine.js — Unit tests for research-engine.js
 */

const assert = require('assert');
const engine = require('../app/js/research-engine.js');

function generateSampleBars(count, trend = 0.001) {
  const bars = [];
  let price = 100.0;
  const startDate = new Date(Date.now() - count * 24 * 60 * 60 * 1000);

  for (let i = 0; i < count; i++) {
    price *= (1 + trend + (Math.random() - 0.48) * 0.02);
    const d = new Date(startDate.getTime() + i * 24 * 60 * 60 * 1000);
    bars.push({
      date: d.toISOString().split('T')[0],
      open: price * 0.995,
      high: price * 1.02,
      low: price * 0.98,
      close: price,
      volume: 500000 + Math.floor(Math.random() * 200000),
    });
  }
  return bars;
}

// Test 1: Empty or insufficient bars
assert.strictEqual(engine.run([]), null, 'Empty array should return null');
assert.strictEqual(engine.run([{ close: 100 }]), null, 'Insufficient bars should return null');

// Test 2: Standard 365-day backtest
const bars365 = generateSampleBars(365, 0.002);
const report = engine.run(bars365, { symbol: 'SAMPLE', evalBars: 250 });

assert.ok(report, 'Report should be generated');
assert.strictEqual(report.symbol, 'SAMPLE');
assert.ok(report.study, 'Report should have study section');
assert.ok(report.simulation, 'Report should have simulation section');
assert.ok(report.verdict, 'Report should have verdict section');
assert.ok(typeof report.study.target_hit_rate_pct === 'number', 'Target hit rate should be a number');
assert.ok(typeof report.simulation.win_rate_pct === 'number', 'Win rate should be a number');

console.log('✅ All research-engine.js unit tests passed successfully!');
