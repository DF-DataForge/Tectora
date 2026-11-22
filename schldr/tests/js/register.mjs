// The editor's library is written the way Odoo loads it: imports without a
// file extension. Node wants one, so the tests add it.
import { register } from "node:module";

register("./resolve.mjs", import.meta.url);
