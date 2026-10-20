// Run with: node --test tests/test_web_node_details.js
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
    constructor() { this.listeners = {}; this.hidden = false; this.value = ''; }
    addEventListener(type, listener) { this.listeners[type] = listener; }
    fire(type) { this.listeners[type](); }
}

function appContext() {
    const elements = {};
    const container = new Element();
    Object.defineProperty(container, 'innerHTML', {
        get() { return this.html; },
        set(html) {
            this.html = html;
            for (const id of Object.keys(elements)) delete elements[id];
            for (const match of html.matchAll(/id="([^"]+)"/g)) elements[match[1]] = new Element();
            for (const direction of ['outgoing', 'incoming']) {
                const list = elements[`${direction}ConnectionList`];
                if (!list) continue;
                const listHtml = html.split(`id="${direction}ConnectionList"`)[1].split('connection-no-matches')[0];
                list.cards = Array.from(listHtml.matchAll(/class="connection-item"/g), () => new Element());
                list.querySelectorAll = () => list.cards;
                elements[`${direction}ConnectionNoMatches`].hidden = true;
            }
            elements.detailsContainer = container;
        },
    });
    elements.detailsContainer = container;
    const context = vm.createContext({
        vis: { DataSet: class {} }, window: {},
        document: { addEventListener() {}, getElementById(id) { return elements[id]; } },
        fetch() { throw new Error('Local filtering must not fetch'); },
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/js/app.js'), 'utf8'), context);
    context.focused = [];
    context.executed = [];
    vm.runInContext('focusOnEdge = id => focused.push(id); executeCommand = host => executed.push(host);', context);
    return { context, elements, container };
}

const outgoing = [
    { edge_id: 0, target: 'Server-A', ip: '10.1.2.3', peer_interfaces: ['FE80::AB'], port: 22,
        user: 'secret-user', method: 'password', creds: 'secret-password', disabled: true },
    { edge_id: 2, target: 'Server-B', ip: '10.2.3.4', port: 2222, method: 'key', creds: '/keys/private-key' },
];
const incoming = [{ edge_id: 3, source: 'Pivot-C', ip: '192.0.2.1', peer_interfaces: ['10.9.8.7'], creds: 'incoming-secret' }];
function display(app, hostname = 'host') {
    app.context.data = { hostname, interfaces: [], outgoing_connections: outgoing, incoming_connections: incoming };
    vm.runInContext('displayNodeDetails(data)', app.context);
}
function filter(app, direction, query) {
    const input = app.elements[`${direction}ConnectionFilter`];
    input.value = query;
    input.fire('input');
    return app.elements[`${direction}ConnectionList`].cards.map(card => card.hidden);
}

test('local filters independently match peer hostname, connection IP and peer interface IP', () => {
    const app = appContext();
    display(app);
    assert.deepEqual(filter(app, 'outgoing', '  SERVER-a  '), [false, true]);
    assert.deepEqual(app.elements.incomingConnectionList.cards.map(c => c.hidden), [false]);
    assert.deepEqual(filter(app, 'outgoing', 'fe80::ab'), [false, true]);
    assert.deepEqual(filter(app, 'outgoing', '10.2.3'), [true, false]);
    assert.deepEqual(filter(app, 'incoming', 'PIVOT'), [false]);
    assert.deepEqual(filter(app, 'incoming', '10.9.8'), [false]);
    assert.deepEqual(filter(app, 'incoming', '192.0.2'), [false]);
    assert.deepEqual(filter(app, 'incoming', 'none'), [true]);
    assert.equal(app.elements.incomingConnectionNoMatches.hidden, false);
    assert.deepEqual(filter(app, 'incoming', ''), [false]);
    assert.equal(app.elements.incomingConnectionNoMatches.hidden, true);
});

test('credentials, user, method and port are displayed but excluded from matching', () => {
    const app = appContext();
    display(app);
    for (const query of ['secret-password', 'private-key', 'secret-user', 'password', '2222']) {
        assert.deepEqual(filter(app, 'outgoing', query), [true, true]);
    }
    assert.deepEqual(filter(app, 'incoming', 'incoming-secret'), [true]);
    assert.match(app.container.innerHTML, /Credentials:.*secret-password/);
    assert.match(app.container.innerHTML, /Credentials:.*\/keys\/private-key/);
    assert.match(app.container.innerHTML, /Credentials:.*incoming-secret/);
    assert.match(app.container.innerHTML, /Disabled/);
    assert.match(app.container.innerHTML, /Enable edge/);
    assert.match(app.container.innerHTML, /event.stopPropagation\(\); toggleEdgeDisabled\(0\)/);
});

test('switching nodes resets filters and cards retain focus interactions', () => {
    const app = appContext();
    display(app);
    filter(app, 'outgoing', 'none');
    filter(app, 'incoming', 'none');
    display(app, 'next');
    assert.equal(app.elements.outgoingConnectionFilter.value, '');
    assert.equal(app.elements.incomingConnectionFilter.value, '');
    assert.deepEqual(app.elements.outgoingConnectionList.cards.map(c => c.hidden), [false, false]);
    assert.equal(app.elements.outgoingConnectionNoMatches.hidden, true);
    app.elements.outgoingConnectionList.cards[0].fire('click');
    assert.deepEqual(Array.from(app.context.focused), [0]);
});

test('all node/card values are escaped, including ports and malicious edge IDs', () => {
    const app = appContext();
    const payload = '\"><img src=x onerror=alert(1)>\'&';
    app.context.data = {
        hostname: payload, interfaces: [payload],
        outgoing_connections: [{ edge_id: payload, target: payload, ip: payload, port: payload,
            user: payload, method: payload, creds: payload }],
        incoming_connections: [{ source: payload, creds: null }],
    };
    vm.runInContext('displayNodeDetails(data)', app.context);
    assert.ok(!app.container.innerHTML.includes(payload));
    assert.ok(!app.container.innerHTML.includes('<img'));
    assert.match(app.container.innerHTML, /&quot;&gt;&lt;img/);
    assert.match(app.container.innerHTML, /Credentials:.*N\/A/);
    app.elements.outgoingConnectionList.cards[0].fire('click');
    assert.equal(app.context.focused.length, 0);
    app.elements.nodeExecuteButton.fire('click');
    assert.equal(app.context.executed[0], payload);
});

test('empty connection lists and missing interfaces render safely', () => {
    const app = appContext();
    app.context.data = { hostname: 'empty' };
    vm.runInContext('displayNodeDetails(data)', app.context);
    assert.equal(app.elements.outgoingConnectionFilter, undefined);
    assert.equal(app.elements.incomingConnectionFilter, undefined);
    assert.match(app.container.innerHTML, /N\/A/);
});
