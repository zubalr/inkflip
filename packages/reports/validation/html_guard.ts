/**
 * Script-free HTML export guard (I10/I09).
 *
 * The human report is a self-contained `.html` with no JavaScript, no
 * forms, no external resources and a meta-CSP locked to
 * `default-src 'none'` plus `img-src data:` for the embedded sanitized
 * PNGs. This module verifies that invariant on the *serialized* export
 * bytes: any active element, event-handler attribute, dangerous URL
 * scheme, external reference or missing CSP fails with
 * ContractError('HTML'). It is the tripwire every exporter — the T16
 * product exporter and the test double alike — must pass before output
 * is considered openable.
 *
 * Also provided: `escapeHtml`, the single escaping rule (text nodes and
 * quoted attributes) the exporter contract relies on. Imported report
 * strings must never reach HTML output unescaped.
 */
import { ContractError } from '../../contracts/src/index.ts';

const fail = (message: string): never => {
  throw new ContractError('HTML', message);
};

/** Escape text/attribute content; equivalent semantics to html.escape(s, quote=True). */
export function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#x27;');
}

/** Elements that are never allowed in a script-free report. */
const FORBIDDEN_ELEMENTS = [
  'script', 'iframe', 'object', 'embed', 'applet', 'form', 'input',
  'button', 'select', 'textarea', 'option', 'fieldset', 'a', 'area',
  'link', 'base', 'meta-refresh', 'video', 'audio', 'source', 'track',
  'picture', 'svg', 'math', 'template', 'slot', 'noscript', 'frameset',
  'frame', 'portal', 'param', 'isindex', 'keygen', 'dialog',
] as const;

/** Attributes that can trigger loads, scripts or navigation. */
const FORBIDDEN_ATTRS = [
  'srcdoc', 'srcset', 'formaction', 'xlink:href', 'data', 'action',
  'background', 'poster', 'href', 'style', 'ping', 'manifest',
  'content', // guarded separately on <meta http-equiv>
] as const;

/** URI schemes that must never appear inside a markup attribute. */
const FORBIDDEN_SCHEMES = ['javascript:', 'vbscript:', 'data:'];

/** URL-ish constructs that must never appear inside the fixed stylesheet. */
const FORBIDDEN_CSS = [
  'url(', '@import', 'expression(', 'behavior:', '-moz-binding',
  '@charset', 'javascript:',
] as const;

/**
 * Decode HTML entities inside an attribute value. Exporters escape `'` and
 * `"` (and an attacker would reach for `&#x…;` to smuggle a scheme), so
 * every value is normalized to its decoded form before any check runs.
 */
function decodeEntities(value: string): string {
  const named: Record<string, string> = {
    amp: '&',
    lt: '<',
    gt: '>',
    quot: '"',
    apos: "'",
    colon: ':',
    sol: '/',
    equals: '=',
    Tab: '\t',
    NewLine: '\n',
  };
  return value.replace(
    /&(#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[a-zA-Z]+);?/g,
    (whole, body: string) => {
      if (body.startsWith('#x') || body.startsWith('#X')) {
        const cp = parseInt(body.slice(2), 16);
        return cp >= 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : whole;
      }
      if (body.startsWith('#')) {
        const cp = parseInt(body.slice(1), 10);
        return cp >= 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : whole;
      }
      return Object.prototype.hasOwnProperty.call(named, body)
        ? named[body]!
        : whole;
    },
  );
}

const META_CSP_RE =
  /<meta\s[^>]*http-equiv\s*=\s*["']?Content-Security-Policy["']?[^>]*>/i;

/** Directives the exported CSP must carry. */
const REQUIRED_CSP = [
  "default-src 'none'",
  "img-src data:",
  "base-uri 'none'",
  "form-action 'none'",
] as const;

/**
 * Verify a serialized export is script-free. `html` is the final document
 * text; throws ContractError('HTML') on any violation. The checks are
 * deliberately lexical — they do not parse or execute the document.
 */
export function assertScriptFreeHtml(html: string): void {
  if (html.includes('\u0000')) fail('NUL byte in export');
  const lower = html.toLowerCase();

  // ---- meta CSP present with the required directives ----------------
  const cspTag = META_CSP_RE.exec(html);
  if (cspTag === null) fail('Missing Content-Security-Policy meta');
  const cspAttr = /content\s*=\s*"([^"]*)"/i.exec(cspTag[0]);
  if (cspAttr === null) fail('CSP meta lacks content attribute');
  const csp = decodeEntities(cspAttr[1]!).toLowerCase().replace(/\s+/g, ' ');
  for (const directive of REQUIRED_CSP) {
    if (!csp.includes(directive)) {
      fail(`CSP missing directive: ${directive}`);
    }
  }

  // ---- forbidden elements ------------------------------------------
  // Scan every tag-like span; the element name and attribute names are
  // checked, so encoded variants like `<SCRIPT>` still match.
  const tagRe = /<\s*\/?\s*([a-zA-Z][a-zA-Z0-9-]*)((?:"[^"]*"|'[^']*'|[^>"'])*)>/g;
  let m: RegExpExecArray | null;
  while ((m = tagRe.exec(html)) !== null) {
    const el = m[1]!.toLowerCase();
    if ((FORBIDDEN_ELEMENTS as readonly string[]).includes(el)) {
      fail(`Forbidden element <${el}>`);
    }
    // Tag-level attribute scan: names/values are consumed left to right
    // and quoted values are skipped whole, so text inside a value (for
    // example the words `onclick=` in an escaped explanation) can never
    // be mistaken for markup.
    const attrs = m[2] ?? '';
    let ai = 0;
    while (ai < attrs.length) {
      while (ai < attrs.length && /\s|\//.test(attrs[ai]!)) ai++;
      if (ai >= attrs.length) break;
      const nameStart = ai;
      while (ai < attrs.length && !/[\s=>/]/.test(attrs[ai]!)) ai++;
      const name = attrs.slice(nameStart, ai).toLowerCase();
      if (name === '') {
        ai++;
        continue;
      }
      while (ai < attrs.length && /\s/.test(attrs[ai]!)) ai++;
      let value = '';
      if (attrs[ai] === '=') {
        ai++;
        while (ai < attrs.length && /\s/.test(attrs[ai]!)) ai++;
        const quote = attrs[ai];
        if (quote === '"' || quote === "'") {
          const end = attrs.indexOf(quote, ai + 1);
          value = attrs.slice(ai + 1, end === -1 ? attrs.length : end);
          ai = end === -1 ? attrs.length : end + 1;
        } else {
          const vStart = ai;
          while (ai < attrs.length && !/[\s>]/.test(attrs[ai]!)) ai++;
          value = attrs.slice(vStart, ai);
        }
      }
      if (name.startsWith('on')) {
        fail(`Event-handler attribute ${name}`);
      }
      if (
        name !== 'content' &&
        (FORBIDDEN_ATTRS as readonly string[]).includes(name)
      ) {
        fail(`Forbidden attribute ${name}`);
      }
      // Attribute values are entity-decoded first so `&#x…;` smuggling
      // and the exporter's own `'` escaping are both normalized away.
      const attrValue = decodeEntities(value).toLowerCase().trim();
      if (name === 'src' && !attrValue.startsWith('data:image/png;base64,')) {
        fail('src attribute is not an embedded PNG data URL');
      }
      // Attribute-level scheme check: javascript:/vbscript:/data: must
      // never appear in any markup attribute value. (In escaped text
      // they are inert — the report can legitimately quote them.) The
      // meta `content` attribute is exempt from `data:` only: the CSP
      // legitimately names `img-src data:`.
      for (const scheme of FORBIDDEN_SCHEMES) {
        if (scheme === 'data:' && name === 'content') continue;
        if (
          attrValue.includes(scheme) &&
          !(name === 'src' && attrValue.startsWith('data:image/png;base64,'))
        ) {
          fail(`Forbidden scheme ${scheme} in attribute ${name}`);
        }
      }
      if (
        name === 'http-equiv' &&
        value.toLowerCase() !== 'content-security-policy'
      ) {
        fail(`Forbidden meta http-equiv ${value}`);
      }
    }
  }

  // ---- stylesheet contents ------------------------------------------
  // CSS constructs are checked only inside <style> blocks: the same
  // tokens are harmless in escaped text and must not fail there.
  const styleRe = /<style[^>]*>([\s\S]*?)<\/style>/gi;
  let sm: RegExpExecArray | null;
  while ((sm = styleRe.exec(html)) !== null) {
    const cssText = sm[1]!.toLowerCase();
    for (const css of FORBIDDEN_CSS) {
      if (cssText.includes(css)) {
        fail(`Forbidden stylesheet construct ${css}`);
      }
    }
  }
  // http-equiv=refresh is covered by the attribute scan; also forbid
  // HTML conditional comments which can smuggle markup for old engines.
  if (lower.includes('<!--[if') || lower.includes('<![endif')) {
    fail('Conditional comment in export');
  }
  // XML processing instructions have no place in the HTML report; their
  // literal presence means something reached output unescaped.
  if (lower.includes('<?')) fail('Processing instruction in export');
  // External resource loads are impossible: every URL-capable attribute
  // is forbidden except the embedded-PNG img src handled above. Text may
  // quote URLs freely — it is never autolinked (there is no <a>).
}
