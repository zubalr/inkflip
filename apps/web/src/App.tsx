import styles from "./styles/App.module.css";

export default function App() {
  return (
    <>
      <header className={styles.header}>
        <span className={styles.brand}>
          <span className={styles.mark} aria-hidden="true">
            if
          </span>
          inkflip
          <span className={styles.descriptor}>PDF reading inspector</span>
        </span>
      </header>
      <main className={styles.main}>
        <p className={styles.eyebrow}>One document. More than one reading.</p>
        <h1 className={styles.headline}>
          Your PDF can look right and <em>read wrong</em>.
        </h1>
        <p className={styles.lede}>
          Compare the page with named text readings. Find a difference, inspect
          its source, and keep the evidence on your device.
        </p>
        <section className={styles.scaffold} aria-label="Scaffold status">
          <h2>Bootstrap scaffold</h2>
          <p>
            This checkout builds the workspace, command harness and visual
            foundation only. Document opening, readers, comparison and export
            are implemented by later tasks. Nothing here processes or transmits
            a file.
          </p>
        </section>
      </main>
    </>
  );
}
