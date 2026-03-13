import styles from "./DesignSystemPage.module.css";
import Button from "@shared/atoms/Button/Button";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import Breadcrumb from "@shared/atoms/Breadcrumb/Breadcrumb.tsx";
import { Types } from "@shared/utils/Types.ts";

export default function DesignSystemPage() {
  const buttonColor: Types = "secondary";

  return (
    <div className={styles.grid}>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"filled"} size={"small"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"outlined"} size={"small"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"text"} size={"small"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"filled"} size={"medium"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"outlined"} size={"medium"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"text"} size={"medium"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"filled"} size={"small"} icon={{ category: "outlined", type: "Add" }}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"outlined"} size={"small"} icon={{ category: "outlined", type: "Add" }}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"text"} size={"small"} icon={{ category: "outlined", type: "Add" }}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"filled"} size={"medium"} icon={{ category: "outlined", type: "Add" }}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"outlined"} size={"medium"} icon={{ category: "outlined", type: "Add" }}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"text"} size={"medium"} icon={{ category: "outlined", type: "Add" }}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <Button disabled color={buttonColor} variant={"filled"} size={"small"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button disabled color={buttonColor} variant={"outlined"} size={"small"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button disabled color={buttonColor} variant={"text"} size={"small"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <Button disabled color={buttonColor} variant={"filled"} size={"medium"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button disabled color={buttonColor} variant={"outlined"} size={"medium"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button disabled color={buttonColor} variant={"text"} size={"medium"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <Button
          disabled
          color={buttonColor}
          variant={"filled"}
          size={"small"}
          icon={{ category: "outlined", type: "Add" }}
        >
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button
          disabled
          color={buttonColor}
          variant={"outlined"}
          size={"small"}
          icon={{ category: "outlined", type: "Add" }}
        >
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button
          disabled
          color={buttonColor}
          variant={"text"}
          size={"small"}
          icon={{ category: "outlined", type: "Add" }}
        >
          Button
        </Button>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <Button
          disabled
          color={buttonColor}
          variant={"filled"}
          size={"medium"}
          icon={{ category: "outlined", type: "Add" }}
        >
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button
          disabled
          color={buttonColor}
          variant={"outlined"}
          size={"medium"}
          icon={{ category: "outlined", type: "Add" }}
        >
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button
          disabled
          color={buttonColor}
          variant={"text"}
          size={"medium"}
          icon={{ category: "outlined", type: "Add" }}
        >
          Button
        </Button>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          color={buttonColor}
          variant={"filled"}
          size={"small"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          color={buttonColor}
          variant={"outlined"}
          size={"small"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          color={buttonColor}
          variant={"icon"}
          size={"small"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          color={buttonColor}
          variant={"filled"}
          size={"medium"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          color={buttonColor}
          variant={"outlined"}
          size={"medium"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          color={buttonColor}
          variant={"icon"}
          size={"medium"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          disabled
          color={buttonColor}
          variant={"filled"}
          size={"small"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          disabled
          color={buttonColor}
          variant={"outlined"}
          size={"small"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          disabled
          color={buttonColor}
          variant={"icon"}
          size={"small"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          disabled
          color={buttonColor}
          variant={"filled"}
          size={"medium"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          disabled
          color={buttonColor}
          variant={"outlined"}
          size={"medium"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          disabled
          color={buttonColor}
          variant={"icon"}
          size={"medium"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <TextInput label={"Input texte"} placeholder={"Placeholder"}></TextInput>
      </div>
      <div className={styles.componentCard}>
        <TextInput label={"Input texte"} placeholder={"Placeholder"} explication={"explication"}></TextInput>
      </div>
      <div className={styles.componentCard}>
        <TextInput label={"Input texte"} placeholder={"Placeholder"} error={"error"}></TextInput>
      </div>
      <div className={styles.componentCard}>
        <TextInput
          label={"Input texte"}
          placeholder={"Placeholder"}
          explication={"explication"}
          error={"error + explication"}
        ></TextInput>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <Breadcrumb
          items={[
            {
              label: "Home",
            },
            {
              label: "Design System",
              callback: () => {
                console.log("clicked");
              },
            },
          ]}
        ></Breadcrumb>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
    </div>
  );
}
