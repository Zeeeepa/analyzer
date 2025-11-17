```typescript
import {
  Controller,
  Get,
  Post,
  Body,
  Patch,
  Param,
  Delete,
  UseGuards,
  ParseIntPipe,
  HttpException,
  HttpStatus,
  Logger,
} from '@nestjs/common';
import { TodosService } from './todos.service';
import { CreateTodoDto } from './dto/create-todo.dto';
import { UpdateTodoDto } from './dto/update-todo.dto';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';

@Controller('todos')
@UseGuards(JwtAuthGuard)
export class TodosController {
  private readonly logger = new Logger(TodosController.name);

  constructor(private readonly todosService: TodosService) {}

  @Post()
  create(@Body() createTodoDto: CreateTodoDto) {
    try {
      this.logger.log(`Creating a new todo with title: "${createTodoDto.title}"`);
      return this.todosService.create(createTodoDto);
    } catch (error) {
      this.logger.error(
        `Failed to create todo. Title: "${createTodoDto.title}"`,
        error.stack,
      );
      throw new HttpException(
        'Failed to create todo due to a server error.',
        HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  @Get()
  findAll() {
    try {
      this.logger.log('Fetching all todos.');
      return this.todosService.findAll();
    } catch (error) {
      this.logger.error('Failed to fetch all todos.', error.stack);
      throw new HttpException(
        'Failed to retrieve todos.',
        HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  @Get(':id')
  findOne(@Param('id', ParseIntPipe) id: number) {
    try {
      this.logger.log(`Fetching todo with id: ${id}`);
      const todo = this.todosService.findOne(id);
      if (!todo) {
        this.logger.warn(`Todo with id ${id} not found.`);
        throw new HttpException(
          `Todo with ID ${id} not found.`,
          HttpStatus.NOT_FOUND,
        );
      }
      return todo;
    } catch (error) {
      if (error instanceof HttpException) {
        throw error;
      }
      this.logger.error(`Failed to fetch todo with id: ${id}`, error.stack);
      throw new HttpException(
        'Failed to retrieve todo.',
        HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  @Patch(':id')
  update(
    @Param('id', ParseIntPipe) id: number,
    @Body() updateTodoDto: UpdateTodoDto,
  ) {
    try {
      this.logger.log(`Updating todo with id: ${id}`);
      const updatedTodo = this.todosService.update(id, updateTodoDto);
      if (!updatedTodo) {
        this.logger.warn(`Todo with id ${id} not found for update.`);
        throw new HttpException(
          `Todo with ID ${id} not found.`,
          HttpStatus.NOT_FOUND,
        );
      }
      return updatedTodo;
    } catch (error) {
      if (error instanceof HttpException) {
        throw error;
      }
      this.logger.error(
        `Failed to update todo with id: ${id}`,
        error.stack,
      );
      throw new HttpException(
        'Failed to update todo.',
        HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  @Delete(':id')
  remove(@Param('id', ParseIntPipe) id: number) {
    try {
      this.logger.log(`Deleting todo with id: ${id}`);
      const deletedTodo = this.todosService.remove(id);
      if (!deletedTodo) {
        this.logger.warn(`Todo with id ${id} not found for deletion.`);
        throw new HttpException(
          `Todo with ID ${id} not found.`,
          HttpStatus.NOT_FOUND,
        );
      }
      return { message: `Todo with ID ${id} has been successfully deleted.` };
    } catch (error) {
      if (error instanceof HttpException) {
        throw error;
      }
      this.logger.error(
        `Failed to delete todo with id: ${id}`,
        error.stack,
      );
      throw new HttpException(
        'Failed to delete todo.',
        HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }
}
```