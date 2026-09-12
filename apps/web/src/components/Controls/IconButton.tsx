import React, { forwardRef } from "react";
import styles from "./IconButton.module.css";

export type AccessibleNameProps =
  | { "aria-label": string; "aria-labelledby"?: never }
  | { "aria-labelledby": string; "aria-label"?: never };

export type IconButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> &
  AccessibleNameProps & {
    bordered?: boolean;
    children: React.ReactNode;
  };

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  {
    bordered = false,
    className,
    children,
    type = "button",
    ...rest
  },
  ref
) {
  const classNames = [
    styles.iconButton,
    bordered ? styles.bordered : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button ref={ref} type={type} className={classNames} {...rest}>
      {children}
    </button>
  );
});

export default IconButton;
