const assert = require("assert");
const { parseCoreResponse } = require("../out/protocol");

const success = parseCoreResponse('{"requestId":7,"ok":true,"data":{"type":"dashboard"}}');
assert.equal(success.requestId, 7);
assert.equal(success.ok, true);
assert.equal(success.data.type, "dashboard");

const failure = parseCoreResponse('{"requestId":8,"ok":false,"error":{"code":"INVALID_REQUEST","message":"bad request"}}');
assert.equal(failure.ok, false);
assert.equal(failure.error.code, "INVALID_REQUEST");
assert.equal(parseCoreResponse("not json"), undefined);
console.log("protocol tests passed");