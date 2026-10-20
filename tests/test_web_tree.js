// Run with: node --test tests/test_web_tree.js
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function appContext() {
    class DataSet {
        constructor(items) { this.items = items; }
        clear() { this.items = []; }
        add(items) { this.items.push(...items); }
    }
    const context = vm.createContext({
        vis: { DataSet }, document: { addEventListener() {} }, window: {},
        clearTimeout() {}, setTimeout() {},
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/js/app.js'), 'utf8'), context);
    vm.runInContext(`
        network = { setOptions() {}, redraw() {} };
        updateStats = () => {};
        updatePhysicsButton = () => {};
    `, context);
    return context;
}

function edge(id, from, to, time = 1, disabled = false, user = 'root') {
    return { id, from, to, time, disabled, user, method: 'password' };
}

const fixture = [
    edge(1, 10, 1), // lower-ID sink is not a root
    edge(2, 0, 2), edge(3, 0, 2, 9), edge(4, 0, 2, 20, true),
    edge(5, 0, 3), edge(6, 2, 3), edge(7, 3, 2),
    edge(8, 20, 21), edge(9, 21, 20), edge(10, 30, 30),
];

function display(context, candidates, selection = null, hops = 1, mode = 'tree', limit = 500) {
    context.candidates = candidates;
    context.selection = selection;
    context.hops = hops;
    context.mode = mode;
    context.limit = limit;
    vm.runInContext(`
        allEdges = candidates;
        allNodes = Array.from(new Set(candidates.flatMap(e => [e.from, e.to])))
            .map(id => ({ id, label: String(id), hostname: String(id), interfaces: [] }));
        selectedNodeId = selection;
        filterState.users = ['root'];
        filterState.methods = ['password'];
        filterState.selectedNodeHops = hops;
        filterState.hopEdgeMode = mode;
        filterState.maxEdges = limit;
        applyFilters();
    `, context);
    return JSON.parse(vm.runInContext('JSON.stringify(edges.items)', context));
}

test('unselected tree renders a directed forest with root ID 0, cycles and parallel edges', () => {
    const displayed = display(appContext(), fixture);
    assert.deepEqual(displayed.map(e => e.id).sort((a, b) => a - b), [1, 3, 5, 8]);
    assert.equal(new Set(displayed.map(e => e.to)).size, displayed.length);
    assert.ok(displayed.some(e => e.from === 0));
});

test('global tree also applies with hops disabled or a selection but zero hops', () => {
    for (const selection of [null, 0]) {
        const displayed = display(appContext(), fixture, selection, 0);
        assert.equal(displayed.length, 4);
    }
});

test('global all mode retains parallel, cycle and self edges', () => {
    assert.equal(display(appContext(), fixture, null, 1, 'all').length, fixture.length);
});

test('attribute filtering precedes forest discovery and limits follow collapse', () => {
    const candidates = Array.from({ length: 100 }, (_, i) => edge(i, 0, 2, i));
    candidates.push(edge(100, 0, 3), edge(101, 0, 4, 200, false, 'other'));
    const displayed = display(appContext(), candidates, null, 1, 'tree', 2);
    assert.deepEqual(displayed.map(e => e.to).sort(), [2, 3]);
});

test('selected ID 0 tree preserves directed BFS depths and ignores global edge limit', () => {
    const candidates = [...fixture, edge(11, 3, 4), edge(12, 2, 5), edge(13, 5, 6)];
    assert.deepEqual(display(appContext(), candidates, 0, 1, 'tree', 1)
        .map(e => e.id).sort((a, b) => a - b), [3, 5]);
    assert.deepEqual(display(appContext(), candidates, 0, 2, 'tree', 1)
        .map(e => e.id).sort((a, b) => a - b), [3, 5, 11, 12]);
});

test('selected all mode keeps parallel consecutive-layer edges only', () => {
    assert.deepEqual(display(appContext(), fixture, 0, 2, 'all', 1)
        .map(e => e.id).sort((a, b) => a - b), [2, 3, 4, 5]);
});
