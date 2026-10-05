const src=require("fs").readFileSync("node_modules/scratch-storage/dist/web/scratch-storage.js","utf8");
const i=src.indexOf("root[");
console.log("umd tail:", JSON.stringify(src.slice(i, i+220)));
const j=src.indexOf("libraryExport");
console.log("libraryExport idx:", j);
