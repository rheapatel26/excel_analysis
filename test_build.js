const { exec } = require('child_process');

exec('cd client && npx tsc -b && npx vite build', (err, stdout, stderr) => {
  const fs = require('fs');
  fs.writeFileSync('build_output.log', `STDOUT:\n${stdout}\n\nSTDERR:\n${stderr}`);
});
