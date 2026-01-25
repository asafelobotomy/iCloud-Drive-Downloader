#!/bin/bash
# Version Bump Script
# Usage: ./scripts/bump_version.sh <new_version>
# Example: ./scripts/bump_version.sh 4.1.0

set -e

if [ -z "$1" ]; then
    echo "Error: No version specified"
    echo "Usage: $0 <new_version>"
    echo "Example: $0 4.1.0"
    exit 1
fi

NEW_VERSION="$1"

# Validate version format (X.Y.Z)
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Error: Version must be in format X.Y.Z (e.g., 4.1.0)"
    exit 1
fi

echo "Updating version to $NEW_VERSION..."

# Get the repository root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Update version in icloud_downloader.py
echo "  → Updating icloud_downloader.py"
sed -i "s/__version__ = \".*\"/__version__ = \"$NEW_VERSION\"/" "$REPO_ROOT/icloud_downloader.py"

# Update version badge in README.md
echo "  → Updating README.md badge"
sed -i "s/version-[0-9]\+\.[0-9]\+\.[0-9]\+/version-$NEW_VERSION/" "$REPO_ROOT/README.md"

# Get today's date
TODAY=$(date +%Y-%m-%d)

# Check if version already exists in CHANGELOG
if grep -q "## \[$NEW_VERSION\]" "$REPO_ROOT/CHANGELOG.md"; then
    echo "  → Version $NEW_VERSION already exists in CHANGELOG.md"
else
    # Add new version section to CHANGELOG.md (after first two lines)
    echo "  → Adding version section to CHANGELOG.md"
    {
        head -n 4 "$REPO_ROOT/CHANGELOG.md"
        echo ""
        echo "## [$NEW_VERSION] - $TODAY"
        echo ""
        echo "### Added"
        echo "- "
        echo ""
        echo "### Changed"
        echo "- "
        echo ""
        echo "### Fixed"
        echo "- "
        echo ""
        echo "---"
        echo ""
        tail -n +5 "$REPO_ROOT/CHANGELOG.md"
    } > "$REPO_ROOT/CHANGELOG.md.tmp"
    mv "$REPO_ROOT/CHANGELOG.md.tmp" "$REPO_ROOT/CHANGELOG.md"
fi

# Verify the changes
echo ""
echo "✓ Version updated successfully!"
echo ""
echo "Verification:"
python3 "$REPO_ROOT/icloud_downloader.py" --version

echo ""
echo "Next steps:"
echo "  1. Edit CHANGELOG.md to add release notes for $NEW_VERSION"
echo "  2. Run tests: python3 -m unittest discover tests/ -q"
echo "  3. Commit changes: git add -A && git commit -m 'Bump version to $NEW_VERSION'"
echo "  4. Tag release: git tag -a v$NEW_VERSION -m 'Release version $NEW_VERSION'"
echo "  5. Push: git push && git push --tags"
