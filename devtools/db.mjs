// Optional local test runtime. Docker Compose remains the intended development stack.
import {PGlite} from '@electric-sql/pglite';
import {PGLiteSocketServer} from '@electric-sql/pglite-socket';
import {vector} from '@electric-sql/pglite-pgvector';
import {fileURLToPath} from 'node:url';
const dataDir=fileURLToPath(new URL('../.local/pgdata',import.meta.url));
const db=await PGlite.create({dataDir,extensions:{vector}});
const server=new PGLiteSocketServer({db,host:'127.0.0.1',port:55432,maxConnections:20});
await server.start();
console.log('Local test PostgreSQL on 127.0.0.1:55432; Ctrl+C to stop.');
process.on('SIGINT',async()=>{await server.stop();await db.close();process.exit(0);});
