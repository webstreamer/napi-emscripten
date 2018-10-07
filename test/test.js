'use strict';
const bindingPath = require.resolve(`./plugin/build/Release/plugin.node`);
console.log(bindingPath)
const cv = require(bindingPath);

const assert = require('assert');

let mat = new cv.Mat(10, 20, cv.CV_8UC3);
// let Size=new cv.Size()
// console.log(Size)
// let mat = new cv.Mat(Size, cv.CV_8UC3);
console.log(mat.type())
console.log(mat.depth())
console.log(mat.channels())
console.log(mat.empty())
let size = mat.size()
console.log(size)
console.log(size.height)
console.log(size.width)
console.log('-------------------------')
let mat2 = new cv.Mat(mat);
console.log(mat2.type())
console.log(mat2.depth())
console.log(mat2.channels())
console.log(mat2.empty())
let size2 = mat2.size()
console.log(size2)
console.log(size2.height)
console.log(size2.width)

// assert.equal(mat.type(), cv.CV_8UC3);
// assert.equal(mat.depth(), cv.CV_8U);
// assert.equal(mat.channels(), 3);
// assert.ok(mat.empty() === false);

// let size = mat.size();
// assert.equal(size.height, 10);
// assert.equal(size.width, 20);

mat.delete();
mat2 = null
size2 = null
size = null
mat = null;
global.gc();