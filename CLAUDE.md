# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Jekyll static site for the Avonlea at Smith Lake community in Florida (avonlea-fl.org). It's hosted on GitHub Pages using the Minimal Mistakes remote theme.

## Build Commands

```bash
# Install dependencies
bundle install

# Build the site
bundle exec jekyll build

# Run local development server (typically at http://localhost:4000)
bundle exec jekyll serve
```

## Architecture

- **Framework:** Jekyll with GitHub Pages
- **Theme:** Minimal Mistakes (remote theme, "air" skin)
- **Deployment:** Automatic via GitHub Pages on push to master

**Key files:**
- `_config.yml` - Jekyll configuration, site metadata, theme settings
- `_data/navigation.yml` - Site navigation menu structure
- `index.md` and `about.md` - Main content pages using front matter
- `CNAME` - Custom domain configuration (avonlea-fl.org)

**Content pages** use Markdown with YAML front matter for layout and metadata. The site currently has two main pages (Home and About) defined in the navigation.
