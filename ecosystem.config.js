module.exports = {
  apps: [
    {
      name: 'osint-console',
      cwd: '/var/www/osint-console/server',
      script: 'venv/bin/gunicorn',
      interpreter: 'none',
      args: '--workers 1 --worker-class gthread --threads 8 --timeout 0 --bind 127.0.0.1:8420 app:app',
      env: {
        PORT: '8420',
      },
      autorestart: true,
      max_restarts: 10,
    },
  ],
};