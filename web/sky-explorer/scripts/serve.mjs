import http from 'node:http';
const worker=(await import('../dist/server/index.js')).default;
const port=Number(process.env.PORT||4173);
http.createServer(async(req,res)=>{
 try {const r=await worker.fetch(new Request(`http://localhost:${port}${req.url}`),{}, {waitUntil:p=>p.catch(()=>{})});res.writeHead(r.status,Object.fromEntries(r.headers));if(r.body)for await(const chunk of r.body)res.write(chunk);res.end();}
 catch(e){res.writeHead(500);res.end(e.message);}
}).listen(port,'127.0.0.1',()=>console.log(`Local: http://localhost:${port}`));
