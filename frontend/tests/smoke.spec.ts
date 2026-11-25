import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("emulator books a clinic appointment, keyboard only, labelled simulated handset", async ({ page }) => {
  await page.goto("/seance/clinic-booking");
  await expect(page.getByText("Simulated handset").first()).toBeVisible();
  const lcd = page.getByTestId("lcd");
  await expect(lcd).toHaveAttribute("aria-live", "polite");

  await page.getByRole("button", { name: "Dial" }).click();
  await expect(lcd).toContainText("CON Select service");

  const keys = page.getByLabel("Your input");
  for (const k of ["1", "c1", "s1", "1", "2468"]) {   // root: book -> clinic -> slot -> confirm -> PIN
    await keys.fill(k);
    await keys.press("Enter");                         // keyboard operable, no mouse
    await expect(keys).toHaveValue("");
  }
  await expect(lcd).toContainText("END");
  await expect(lcd).toContainText("code:");
  await expect(page.locator("code", { hasText: "2468" })).toHaveCount(1); // only the demo-PIN hint
  await expect(lcd).not.toContainText("2468");
});

test("crypt sample is read-only and shows Last Rites", async ({ page }) => {
  await page.goto("/crypt/clinic-booking");
  await expect(page.getByText("Sample (read-only)").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Compile" })).toHaveCount(0);
  await page.getByRole("tab", { name: "Last Rites" }).click();
  await expect(page.getByText(/validators passed/)).toBeVisible();
  await page.getByRole("tab", { name: "Reanimate" }).click();
  await expect(page.getByText("deterministic").first()).toBeVisible();
});

test("fully refused sample lists each buried operation with its refusal code", async ({ page }) => {
  await page.goto("/crypt/unsupported-demo");
  await expect(page.getByRole("heading", { name: "Buried" })).toBeVisible();
  for (const code of ["R_DATETIME", "R_NESTED_OBJECT", "R_FREE_TEXT", "R_BINARY", "R_POLYMORPHIC"]) {
    await expect(page.locator("code", { hasText: code })).toHaveCount(1);
  }
  await expect(page.getByText("Every operation was refused; no bundle was produced.")).toBeVisible();
});

for (const path of ["/", "/seance/clinic-booking", "/crypt", "/judges", "/login"]) {
  test(`a11y: no serious violations on ${path}`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const res = await new AxeBuilder({ page }).analyze();
    const bad = res.violations.filter(v => v.impact === "serious" || v.impact === "critical");
    expect(bad.map(v => `${v.id}: ${v.nodes[0]?.target}`)).toEqual([]);
  });
}

test("state graph puts every state on the canvas (an unreachable error exit must not push the view off-screen)", async ({ page }) => {
  await page.goto("/crypt/clinic-booking");
  await page.getByRole("tab", { name: "Reanimate" }).click();
  const nodes = page.locator(".react-flow__node");
  await expect(nodes.first()).toBeVisible();
  const canvas = await page.getByLabel("State graph canvas").boundingBox();
  const count = await nodes.count();
  expect(count).toBeGreaterThan(5);
  let inside = 0;
  for (let i = 0; i < count; i++) {
    const b = await nodes.nth(i).boundingBox();
    if (b && canvas && b.x >= canvas.x - 1 && b.x + b.width <= canvas.x + canvas.width + 1) inside++;
  }
  expect(inside).toBe(count);
});

test("emulator accepts the next input while the SMS inbox is still loading (slow host)", async ({ page }) => {
  // Regression: the inbox refresh was awaited inside the send, so the next Enter was dropped on a slow host.
  await page.route("**/api/v1/emulator/inbox/**", async route => {
    await new Promise(r => setTimeout(r, 3_000));
    await route.continue();
  });
  await page.goto("/seance/clinic-booking");
  await page.getByRole("button", { name: "Dial" }).click();
  const lcd = page.getByTestId("lcd");
  await expect(lcd).toContainText("CON Select service");
  const keys = page.getByLabel("Your input");
  await keys.fill("1");
  await keys.press("Enter");
  await expect(lcd).toContainText("Clinic id");
  await keys.fill("c1");
  await keys.press("Enter");                     // inbox request from the first send is still in flight
  await expect(lcd).toContainText("Slot id", { timeout: 2_000 });
});
