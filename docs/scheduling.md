# Scheduling

The workflow currently triggers on:
- **`schedule`**: every 15 minutes by default, automatically. every 15 minutes by default. GitHub's cron is not precise and can run late; see the Cloudflare section below if that matters to you.
- **`workflow_dispatch`**: manually, including from the GitHub Mobile
  app, so you can check on demand without opening a laptop. Manual triggers spin up with no delays.

## Setting up a Cloudflare Worker as a High Frequency Scheduler (Optional)

GitHub's cron scheduler is known to occasionally delay scheduled runs during periods of heavy load. Even if you set up `cron` for 15 minutes, it will spin up in the range of every 30 to 40 minutes or even more depending on the time of the day, which is acceptable to some people, however, if you demand a more consistent high-frequency scheduler, you can let Cloudflare Worker wake up your GitHub workflow instead. It is easy to set up and will cost you nothing as well.

> Cloudflare Worker's sole responsibility is to wake the GitHub workflow on a schedule; all Qoffee logic continues to execute entirely within GitHub Actions, keeping scheduling cleanly separated from monitoring and notification logic. This separation also allows the scheduler to be replaced or removed at any time without requiring any changes to Qoffee itself.

### 1. Create a Cloudflare Worker

1. Sign in to Cloudflare.
2. Navigate to **Workers & Pages**.
3. Create a new Worker.
4. Replace the default code with the Worker below.
5. Deploy the Worker.

### 2. Add Worker Secrets

Under **Settings → Variables and Secrets**, create the following secrets.

| Secret         | Value                                                                                                             |
| -------------- | ----------------------------------------------------------------------------------------------------------------- |
| `GITHUB_REPO`  | `your-username/your-repository`                                                                                   |
| `GITHUB_TOKEN` | A GitHub Fine-Grained Personal Access Token with **Actions: Read & Write** permission for your Qoffee repository. |

### 3. Worker Code

```javascript
export default {
  async scheduled(event, env, ctx) {
    console.log("Qoffee scheduler triggered");

    ctx.waitUntil(triggerWorkflow(env));
  },

  async fetch(request, env, ctx) {
    return new Response("Qoffee scheduler alive");
  }
};

async function triggerWorkflow(env) {
  const url =
    `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/watch.yml/dispatches`;

  console.log("Dispatch URL:", url);

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "qoffee-cloudflare-scheduler"
    },
    body: JSON.stringify({
      ref: "main"
    })
  });

  const text = await response.text();

  console.log("GitHub status:", response.status);
  console.log("GitHub response:", text);

  if (!response.ok) {
    console.log("✗ GitHub workflow dispatch failed");
  } else {
    console.log("✓ GitHub workflow dispatched");
  }
}
```

### 4. Configure the Cron Trigger

From the Worker dashboard:

> **Settings → Triggers → Cron Triggers**

Create a cron schedule such as:

```text
*/5 * * * *
```

This runs the scheduler every five minutes.

Cloudflare cron expressions use UTC time and changes may take several minutes to propagate globally after being saved.

### 5. Generate a GitHub Token

Create a **Fine-Grained Personal Access Token** with access only to your selected Qoffee repository.

Required repository permissions:

* **Actions:** Read and Write
* **Metadata:** Read (automatically included)

Copy the token into the Cloudflare `GITHUB_TOKEN` secret.

### 6. Test the Scheduler

After deployment, you should see logs similar to:

```text
Qoffee scheduler triggered
Dispatch URL: https://api.github.com/repos/your-name/your-repo/actions/workflows/watch.yml/dispatches
GitHub status: 204
GitHub response:
✓ GitHub workflow dispatched
```

An HTTP **204 No Content** response is the expected success response from GitHub when a workflow dispatch request is accepted.

### 7. Verify the Workflow

Open your repository's **Actions** tab.

Every time the Cloudflare cron fires, a new **Qoffee Watcher** workflow run should appear.


> That's it.