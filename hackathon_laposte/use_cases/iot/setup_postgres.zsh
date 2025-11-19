#!/usr/bin/env zsh

set -e  # Exit immediately on error

echo "🚀 Installing and configuring PostgreSQL..."

# 1️⃣ Install PostgreSQL if it's not already installed
if ! command -v psql >/dev/null 2>&1; then
  echo "📦 Installing PostgreSQL..."
  sudo apt update -y
  sudo apt install -y postgresql postgresql-contrib
else
  echo "✅ PostgreSQL is already installed."
fi

# 2️⃣ Start PostgreSQL service
echo "▶️ Starting PostgreSQL service..."
sudo service postgresql start

# 3️⃣ Set password for postgres user
echo "🔑 Setting password for user 'postgres'..."
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'postgres';"

# 4️⃣ Create the database if it doesn't exist
DB_EXISTS=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='base_database'")
if [ "$DB_EXISTS" != "1" ]; then
  echo "🆕 Creating database 'base_database'..."
  sudo -u postgres createdb base_database
else
  echo "✅ Database 'base_database' already exists."
fi

# 5️⃣ Ensure password-based authentication (md5)
PG_HBA=$(find /etc/postgresql -name pg_hba.conf | head -n 1)
echo "⚙️  Configuring password-based access in $PG_HBA ..."
sudo sed -i 's/^\(local[[:space:]]\+all[[:space:]]\+postgres[[:space:]]\+\)peer/\1md5/' "$PG_HBA"

# 6️⃣ Restart PostgreSQL to apply changes
echo "🔄 Restarting PostgreSQL service..."
sudo service postgresql restart

# 7️⃣ Test the connection
echo "🧪 Testing PostgreSQL connection..."
PGPASSWORD=postgres psql -h localhost -U postgres -d base_database -c '\l' || {
  echo "❌ Connection to the database failed. Please check your setup." >&2
  exit 1
}

echo "✅ PostgreSQL is ready, and the database 'base_database' is available!"
